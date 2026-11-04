"""One native progression, independent purchase cutoffs and late pedagogical closure."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from dateutil.relativedelta import relativedelta
from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.addons.training_elearning.tests.test_human_practical import HumanCase


@tagged("post_install", "-at_install")
class TestPurchaseReports(HumanCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commercial = new_test_user(
            cls.env, login="fictional_report_coordinator", groups="training_elearning_sale.group_learning_sales_manager"
        )
        cls.buyer = cls.env["res.partner"].create({"name": "Fictional report purchaser"})

    def buy(self, course, months=1, **policy):
        product = (
            self.env["product.product"]
            .with_user(self.commercial)
            .create(
                {
                    "name": "Fictional scoped course offer",
                    "type": "service",
                    "learning_channel_id": course.id,
                    "learning_access_months": months,
                    **policy,
                }
            )
        )
        order = (
            self.env["sale.order"]
            .with_user(self.commercial)
            .create(
                {
                    "partner_id": self.buyer.id,
                    "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 1})],
                }
            )
        )
        order.action_confirm()
        order.order_line.action_learning_authorize("Fictional scoped purchase approval")
        seat = (
            self.env["training.elearning.sale.allocation"]
            .with_user(self.commercial)
            .create(
                {
                    "line_id": order.order_line.id,
                    "partner_id": self.learner.partner_id.id,
                }
            )
        )
        seat.action_learning_activate()
        return seat

    def test_later_funder_progress_is_excluded_even_before_first_old_report_read(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        first = self.buy(course)
        end = first.access_ends_at
        with patch.object(fields.Datetime, "now", return_value=end - timedelta(days=3)):
            second = self.buy(course, 6)
        self.assertEqual(first.membership_id, second.membership_id)
        with patch.object(fields.Datetime, "now", return_value=end + timedelta(days=1)):
            self.env["training.elearning.service"].with_user(self.learner)._declare(first.membership_id.id, slide.id)
            old = first._purchase_summary()
            current = second._purchase_summary()
        self.assertEqual(old["percentage"], 0)
        self.assertFalse(old["complete"])
        self.assertEqual(old["closed_at"], end)
        self.assertEqual(current["percentage"], 100)
        self.assertTrue(first.membership_id.completion_date)
        with patch.object(fields.Datetime, "now", return_value=end + timedelta(days=2)):
            self.assertEqual(first._purchase_summary(), old)
        with self.assertRaises(AccessError):
            first.report_course_ids.write({"snapshot": {"percentage": 100}})
        with self.assertRaises(AccessError):
            first.report_course_ids.with_user(self.learner).read(["snapshot"])

    def test_preexisting_acquisitions_are_captured_at_new_purchase_without_revealing_origin(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        first = self.buy(course)
        self.env["training.elearning.service"].with_user(self.learner)._declare(first.membership_id.id, slide.id)
        second = self.buy(course)
        result = second._purchase_summary()
        self.assertTrue(result["complete"])
        self.assertEqual(result["percentage"], 100)
        self.assertNotIn("origin", result)
        self.assertNotIn("baseline", result)

    def test_late_human_validation_keeps_full_report_period_after_final_closure(self):
        course, slide, _task, member = self.human()
        seat = self.buy(course)
        end = seat.access_ends_at
        with patch.object(fields.Datetime, "now", return_value=end - timedelta(days=1)):
            row = (
                self.env["training.elearning.practical.service"]
                .with_user(self.learner)
                ._deposit(member.id, slide.id, [("fictional.txt", b"PRIVATE REPORT WORK")], str(uuid4()))
            )
        with patch.object(fields.Datetime, "now", return_value=end + timedelta(days=2)):
            self.assertTrue(seat._purchase_summary()["pending"])
            review = self.publish(row.review_queue_id, outcome="validated", passed=True)
            self.assertTrue(seat._purchase_summary()["pending"])
            self.sent(review.delivery_notice_id)
            result = seat._purchase_summary()
            self.assertTrue(result["complete"])
            self.assertFalse(result["pending"])
            self.assertEqual(result["closed_at"], fields.Datetime.now())
            representative = new_test_user(
                self.env, login="fictional_report_representative", groups="base.group_portal"
            )
            mandate = (
                self.env["training.elearning.sale.mandate"]
                .with_user(self.commercial)
                .create(
                    {
                        "line_id": seat.line_id.id,
                        "user_id": representative.id,
                        "valid_until": end + timedelta(days=500),
                        "reason": "Fictional report mandate",
                    }
                )
            )
            mandate.action_grant()
            service = self.env["training.elearning.company.service"].with_user(representative)
            self.assertEqual(service._ends_at(mandate), result["closed_at"] + relativedelta(months=3))
            self.assertTrue(service._view(mandate.id)["rows"][0]["summary"]["complete"])

    def test_late_revision_uses_original_feedback_and_preserves_pending_due_date(self):
        course, slide, _task, member = self.human()
        seat = self.buy(course)
        end = seat.access_ends_at
        service = self.env["training.elearning.practical.service"].with_user(self.learner)
        with patch.object(fields.Datetime, "now", return_value=end - timedelta(days=1)):
            original = service._deposit(member.id, slide.id, [("first.txt", b"PRIVATE FIRST")], str(uuid4()))
        with patch.object(fields.Datetime, "now", return_value=end + timedelta(days=2)):
            review = self.publish(original.review_queue_id)
            self.sent(review.delivery_notice_id)
            self.assertTrue(seat._purchase_summary()["pending"])
            revised = service._deposit(member.id, slide.id, [("revision.txt", b"PRIVATE REVISION")], str(uuid4()))
            self.assertEqual(revised.revision_parent_id, review)
            self.assertTrue(seat._purchase_summary()["pending"])
        with patch.object(fields.Datetime, "now", return_value=end + timedelta(days=4)):
            final = self.publish(revised.review_queue_id, outcome="validated", passed=True)
            self.sent(final.delivery_notice_id)
            result = seat._purchase_summary()
            self.assertTrue(result["complete"])
            self.assertFalse(result["pending"])
            self.assertEqual(result["closed_at"], fields.Datetime.now())
            frozen = seat.report_course_ids.snapshot
            final.delivery_notice_id._store({"failed": True, "state": "exception"})
            self.assertTrue(seat._purchase_summary()["pending"])
            self.assertFalse(seat.report_course_ids.closed_at)
            with self.assertRaises(AccessError):
                seat.report_course_ids.read(["snapshot_history"])
            self.assertEqual(seat.report_course_ids.sudo().snapshot_history[-1]["summary"], frozen)

    def test_cumulative_revision_right_does_not_extend_other_purchase_report(self):
        course, slide, _task, member = self.human()
        first = self.buy(course, learning_review_days=3, learning_revision_days=21)
        second = self.buy(course, learning_review_days=7, learning_revision_days=28)
        end = max(first.access_ends_at, second.access_ends_at)
        service = self.env["training.elearning.practical.service"].with_user(self.learner)
        with patch.object(fields.Datetime, "now", return_value=end - timedelta(days=1)):
            original = service._deposit(member.id, slide.id, [("first.txt", b"PRIVATE SHARED WORK")], str(uuid4()))
            queue = original.review_queue_id
            item = member._learning_plan()["slides"][0]
            calendar = self.env["resource.calendar"].browse(item["review_calendar"])
            self.assertEqual(queue.due_at, calendar._learning_deadline(original.received_at, 3))
        sent = end + timedelta(days=2)
        with patch.object(fields.Datetime, "now", return_value=sent):
            review = self.publish(queue)
            self.sent(review.delivery_notice_id)
            self.assertEqual(queue.revision_until, sent + timedelta(days=28))
        with patch.object(fields.Datetime, "now", return_value=sent + timedelta(days=25)):
            revised = service._deposit(member.id, slide.id, [("revision.txt", b"PRIVATE LATER REVISION")], str(uuid4()))
            final = self.publish(revised.review_queue_id, outcome="validated", passed=True)
            self.sent(final.delivery_notice_id)
            earlier = first._purchase_summary()
            later = second._purchase_summary()
            self.assertFalse(earlier["complete"])
            self.assertEqual(earlier["closed_at"], sent + timedelta(days=21))
            self.assertTrue(later["complete"])
            self.assertEqual(later["closed_at"], fields.Datetime.now())
            self.assertEqual(first.membership_id, second.membership_id)

    def test_exact_period_end_does_not_attribute_another_funders_completion(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        first = self.buy(course)
        second = self.buy(course, 6)
        with patch.object(fields.Datetime, "now", return_value=first.access_ends_at):
            self.env["training.elearning.service"].with_user(self.learner)._declare(first.membership_id.id, slide.id)
            self.assertEqual(first._purchase_summary()["percentage"], 0)
            self.assertEqual(second._purchase_summary()["percentage"], 100)
        evidence = self.env["slide.slide.partner"].search(
            [
                ("slide_id", "=", slide.id),
                ("partner_id", "=", self.learner.partner_id.id),
            ]
        )
        with self.assertRaises(AccessError):
            evidence.with_user(self.commercial).write({"learning_completed_at": first.access_started_at})
        with self.assertRaises(AccessError):
            self.env["ir.attachment"].with_user(self.commercial).create(
                {
                    "name": "Fictional forbidden report file",
                    "res_model": "training.elearning.sale.course.report",
                    "res_id": first.report_course_ids.id,
                    "type": "url",
                    "url": "https://example.invalid/private",
                }
            )

    def test_invalidation_rectifies_old_snapshot_without_later_funder_credit(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        first = self.buy(course)
        end = first.access_ends_at
        service = self.env["training.elearning.service"].with_user(self.learner)
        with patch.object(fields.Datetime, "now", return_value=end - timedelta(days=2)):
            second = self.buy(course, 6)
            service._declare(first.membership_id.id, slide.id)
        with patch.object(fields.Datetime, "now", return_value=end + timedelta(days=1)):
            old = first._purchase_summary()
            self.assertTrue(old["complete"])
        invalidated = end + timedelta(days=2)
        with patch.object(fields.Datetime, "now", return_value=invalidated):
            self.env["training.elearning.acquisition.invalidation"].with_user(self.pedagogy)._invalidate(
                first.membership_id, slide.id, "Fictional corrected acquisition", str(uuid4())
            )
            revised = first._purchase_summary()
            self.assertFalse(revised["complete"])
            self.assertEqual(revised["closed_at"], invalidated)
            history = first.report_course_ids.sudo().snapshot_history
            self.assertEqual(history[-1]["summary"]["complete"], True)
            self.assertEqual(history[-1]["at"], fields.Datetime.to_string(end))
        with patch.object(fields.Datetime, "now", return_value=end + timedelta(days=3)):
            service._declare(first.membership_id.id, slide.id)
            self.assertEqual(first._purchase_summary(), revised)
            self.assertTrue(second._purchase_summary()["complete"])
        with patch.object(fields.Datetime, "now", return_value=end + timedelta(days=4)):
            self.env["training.elearning.acquisition.invalidation"].with_user(self.pedagogy)._invalidate(
                first.membership_id, slide.id, "Fictional later funding decision", str(uuid4())
            )
            self.assertEqual(first._purchase_summary(), revised)
            self.assertFalse(second._purchase_summary()["complete"])

    def test_human_invalidation_keeps_pending_candidate_and_due_date(self):
        course, slide, _task, member = self.human()
        seat = self.buy(course)
        service = self.env["training.elearning.practical.service"].with_user(self.learner)
        original = service._deposit(member.id, slide.id, [("first.txt", b"Fictional original")], str(uuid4()))
        review = self.publish(original.review_queue_id, outcome="validated", passed=True)
        self.sent(review.delivery_notice_id)
        self.assertTrue(seat._purchase_summary()["complete"])
        candidate = service._deposit(member.id, slide.id, [("next.txt", b"Fictional pending candidate")], str(uuid4()))
        queue = candidate.review_queue_id
        clock = queue.read(["first_received_at", "due_at", "submission_id", "state"])
        event = (
            self.env["training.elearning.acquisition.invalidation"]
            .with_user(self.pedagogy)
            ._invalidate(member, slide.id, "Fictional human validation decision", str(uuid4()))
        )
        self.assertEqual(queue.read(["first_received_at", "due_at", "submission_id", "state"]), clock)
        self.assertFalse(seat._purchase_summary()["complete"])
        self.assertEqual(member.completion, 0)
        new_review = self.publish(queue, outcome="validated", passed=True)
        self.sent(new_review.delivery_notice_id)
        self.assertTrue(seat._purchase_summary()["complete"])
        self.assertTrue(event.restored_at)
        self.assertTrue(original.review_id)
