"""Real Sales, memberships and Survey evidence without any TM business dependency."""

from unittest import SkipTest
from unittest.mock import patch
from dateutil.relativedelta import relativedelta
from odoo import fields, Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


class SalesCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "training.elearning.exam.service" not in cls.env:
            raise SkipTest("Shared exam adapter is optional; this integration test requires it")
        cls.company = cls.env.company
        cls.company.email = "fictional-sender@example.invalid"
        cls.manager = new_test_user(
            cls.env, login="fictional_sales_coordinator", groups="training_elearning_sale.group_learning_sales_manager"
        )
        cls.author = new_test_user(
            cls.env, login="fictional_exam_author", groups="training_elearning_survey.group_learning_exam_reader"
        )
        cls.salesperson = new_test_user(cls.env, login="fictional_salesperson", groups="sales_team.group_sale_salesman")
        cls.learner = new_test_user(cls.env, login="fictional_sales_learner", groups="base.group_portal")
        cls.other = new_test_user(cls.env, login="fictional_sales_other", groups="base.group_portal")
        cls.buyer = cls.env["res.partner"].create({"name": "Fictional purchasing company", "is_company": True})
        cls.catalog = cls.env["training.course"].create({"name": "Fictional sold catalogue"})

    def offer(self):
        exam = (
            self.env["survey.survey"]
            .with_user(self.author)
            .create(
                {
                    "title": "Fictional sold shared exam",
                    "training_course_id": self.catalog.id,
                    "time_limit": 10,
                    "scoring_success_min": 75,
                }
            )
        )
        self.env["survey.question"].with_user(self.author).create(
            {
                "survey_id": exam.id,
                "title": "Fictional sold question",
                "question_type": "simple_choice",
                "answer_score": 2,
                "suggested_answer_ids": [
                    Command.create({"value": "Expected", "is_correct": True}),
                    Command.create({"value": "Other"}),
                ],
            }
        )
        exam.action_mock_publish()
        course = (
            self.env["slide.channel"]
            .with_user(self.author)
            .create({"name": "Fictional sold edition", "training_course_id": self.catalog.id})
        )
        slide = (
            self.env["slide.slide"]
            .with_user(self.author)
            .create(
                {
                    "channel_id": course.id,
                    "survey_id": exam.id,
                    "learning_exam_obligation": "pass",
                    "is_published": True,
                }
            )
        )
        course.action_learning_publish()
        product = (
            self.env["product.product"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional autonomous seat",
                    "type": "service",
                    "list_price": 100,
                    "learning_channel_id": course.id,
                }
            )
        )
        return course, slide, product

    def order(self, product, qty=1, kind="initial"):
        order = self.env["sale.order"].with_user(self.manager).create({"partner_id": self.buyer.id})
        line = (
            self.env["sale.order.line"]
            .with_user(self.manager)
            .create(
                {"order_id": order.id, "product_id": product.id, "product_uom_qty": qty, "learning_purchase_kind": kind}
            )
        )
        return order, line

    def seat(self, line, learner=None):
        return (
            self.env["training.elearning.sale.allocation"]
            .with_user(self.manager)
            .create({"line_id": line.id, "partner_id": (learner or self.learner).partner_id.id})
        )


@tagged("post_install", "-at_install")
class TestAutonomousSales(SalesCase):
    def test_native_state_write_cannot_fake_confirmed_contract_or_authorize_retired_offer(self):
        _course, _slide, product = self.offer()
        order, line = self.order(product)
        order.write({"state": "sale"})
        self.assertFalse(line.learning_confirmed_at)
        with self.assertRaises(ValidationError):
            line.action_learning_authorize("Fictional forged native state without confirmation")
        retired_order, _retired_line = self.order(product)
        product.write({"active": False})
        with self.assertRaises(ValidationError):
            retired_order.action_confirm()

    def test_confirmation_authorization_named_access_and_frozen_contract(self):
        course, slide, product = self.offer()
        order, line = self.order(product, 2)
        seat = self.seat(line)
        with self.assertRaises(ValidationError):
            seat.action_learning_activate()
        order.action_confirm()
        self.assertFalse(seat.membership_id)
        self.assertFalse(line.learning_authorized_at)
        self.assertFalse(self.env["slide.channel.partner"].search([("channel_id", "=", course.id)]))
        with self.assertRaises(ValidationError):
            slide.with_user(self.author).write({"learning_exam_obligation": "optional"})
        with self.assertRaises(AccessError):
            line.with_user(self.salesperson).action_learning_authorize("Rejected")
        line.action_learning_authorize("Fictional payment verified")
        deadline = line.learning_assign_until
        self.assertEqual(deadline, line.learning_authorized_at + relativedelta(months=3))
        line.action_learning_authorize("Repeated verification")
        self.assertEqual(line.learning_assign_until, deadline)
        order.write({"user_id": self.salesperson.id})
        with self.assertRaises(AccessError):
            line.with_user(self.salesperson).read(["learning_authorization_reason", "learning_allocation_ids"])
        with self.assertRaises(ValidationError):
            line.write({"product_uom_qty": 3})
        product.write({"learning_access_months": 12, "learning_assignment_months": 1})
        self.assertEqual(line.learning_access_months, 6)
        self.assertEqual(line.learning_assignment_months, 3)
        seat.action_learning_activate()
        member = seat.membership_id
        self.assertEqual(seat.access_ends_at, seat.activated_at + relativedelta(months=6))
        requirements = (
            self.env["training.elearning.exam.requirement"].sudo().search([("membership_id", "=", member.id)])
        )
        self.assertEqual(requirements.exam_id, slide.with_user(self.author).survey_id)
        self.assertEqual(requirements.obligation, "pass")
        self.assertTrue(seat.notification_mail_id)
        mail = seat.notification_mail_id
        end = member.learning_ends_at
        seat.action_learning_activate()
        self.assertEqual(member.learning_ends_at, end)
        self.assertEqual(seat.notification_mail_id, mail)
        mail.sudo().write({"state": "exception"})
        self.env["training.elearning.sale.allocation"]._cron_learning_notifications()
        self.assertEqual(seat.notification_state, "exception")
        activities = seat.activity_ids
        self.env["training.elearning.sale.allocation"]._cron_learning_notifications()
        self.assertEqual(seat.activity_ids, activities)
        self.assertEqual(member.partner_id, self.learner.partner_id)
        self.assertNotEqual(member.partner_id, self.buyer)
        attempt = self.env["training.elearning.exam.service"].with_user(self.learner)._start(member.id, slide.id)
        self.assertEqual(attempt.mock_context_key, "slide.channel.partner:%s" % member.id)
        self.assertFalse(attempt.with_user(self.manager).search([("id", "=", attempt.id)]))
        with self.assertRaises(AccessError):
            seat.with_user(self.learner).read(["line_id"])
        with self.assertRaises(AccessError):
            seat.with_user(self.salesperson).action_learning_activate()

    def test_renewal_keeps_obligations_attempt_deadline_and_single_membership(self):
        course, slide, product = self.offer()
        order, line = self.order(product)
        order.action_confirm()
        line.action_learning_authorize("Fictional agreement")
        first = self.seat(line)
        first.action_learning_activate()
        member = first.membership_id
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slide.id)
        deadline = attempt.deadline
        requirements = (
            self.env["training.elearning.exam.requirement"].sudo().search([("membership_id", "=", member.id)])
        )
        renewal_order, renewal = self.order(product, kind="renewal")
        renewal_order.action_confirm()
        renewal.action_learning_authorize("Fictional renewal agreement")
        seat = self.seat(renewal)
        old_end = member.learning_ends_at
        seat.action_learning_activate()
        self.assertEqual(seat.membership_id, member)
        self.assertEqual(seat.access_started_at, old_end)
        self.assertEqual(member.learning_ends_at, old_end + relativedelta(months=6))
        self.assertEqual(service._start(member.id, slide.id), attempt)
        self.assertEqual(attempt.deadline, deadline)
        self.assertEqual(
            requirements,
            self.env["training.elearning.exam.requirement"].sudo().search([("membership_id", "=", member.id)]),
        )
        self.assertEqual(
            self.env["slide.channel.partner"].search_count(
                [("channel_id", "=", course.id), ("partner_id", "=", self.learner.partner_id.id)]
            ),
            1,
        )
        other_order, other_line = self.order(product)
        other_order.action_confirm()
        other_line.action_learning_authorize("Fictional duplicate purchase")
        with self.assertRaises(ValidationError):
            self.seat(other_line).action_learning_activate()
        renewal_order.action_cancel()
        self.assertEqual(member.learning_ends_at, old_end + relativedelta(months=6))
        self.assertEqual(attempt.state, "in_progress")

    def test_capacity_deadline_metadata_tampering_company_and_cancelled_order(self):
        course, slide, product = self.offer()
        order, line = self.order(product)
        seat = self.seat(line)
        with self.assertRaises(ValidationError):
            self.seat(line, self.other)
        with self.assertRaises(ValidationError):
            line.write({"product_uom_qty": 0})
        with self.assertRaises(AccessError):
            seat.write({"activated_at": False})
        with self.assertRaises(AccessError):
            line.write({"learning_authorized_at": False})
        with self.assertRaises(AccessError):
            self.env["training.elearning.sale.allocation"].with_user(self.manager).with_context(
                default_activated_at=False
            ).create({"line_id": line.id, "partner_id": self.other.partner_id.id})
        order.action_confirm()
        line.action_learning_authorize("Fictional verification")
        with patch.object(fields.Datetime, "now", return_value=line.learning_assign_until):
            with self.assertRaises(ValidationError):
                seat.action_learning_activate()
        foreign = self.env["res.company"].create({"name": "Fictional foreign operator"})
        manager = new_test_user(
            self.env,
            login="fictional_foreign_sales",
            groups="training_elearning_sale.group_learning_sales_manager",
            company_id=foreign.id,
            company_ids=[Command.set(foreign.ids)],
        )
        self.assertFalse(seat.with_user(manager).search([("id", "=", seat.id)]))
        with self.assertRaises(AccessError):
            seat.with_user(manager).action_learning_activate()
        order.action_cancel()
        with self.assertRaises(ValidationError):
            seat.action_learning_activate()
        self.assertFalse(seat.membership_id)

    def test_partial_authorization_and_notification_failure_do_not_open_other_context(self):
        first, slide, product = self.offer()
        second = (
            self.env["slide.channel"]
            .with_user(self.author)
            .create({"name": "Fictional second sold context", "training_course_id": self.catalog.id})
        )
        other_slide = (
            self.env["slide.slide"]
            .with_user(self.author)
            .create(
                {
                    "channel_id": second.id,
                    "survey_id": slide.with_user(self.author).survey_id.id,
                    "learning_exam_obligation": "complete",
                    "is_published": True,
                }
            )
        )
        second.action_learning_publish()
        other_product = (
            self.env["product.product"]
            .with_user(self.manager)
            .create({"name": "Fictional second context seat", "type": "service", "learning_channel_id": second.id})
        )
        order, line = self.order(product)
        other = (
            self.env["sale.order.line"]
            .with_user(self.manager)
            .create({"order_id": order.id, "product_id": other_product.id, "product_uom_qty": 1})
        )
        order.action_confirm()
        line.action_learning_authorize("Fictional first line only")
        seat = self.seat(line)
        blocked = self.seat(other)
        with self.assertRaises(ValidationError):
            blocked.action_learning_activate()
        with patch.object(
            type(self.env["mail.template"]),
            "send_mail",
            side_effect=ValidationError("Fictional mail preparation failure"),
        ):
            seat.action_learning_activate()
        self.assertEqual(seat.notification_state, "exception")
        self.assertTrue(seat.activity_ids)
        self.assertEqual(seat.membership_id.learning_state, "active")
        self.assertFalse(blocked.membership_id)
        other.action_learning_authorize("Fictional second line agreement")
        blocked.action_learning_activate()
        self.assertNotEqual(seat.membership_id, blocked.membership_id)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        with self.assertRaises(AccessError):
            service._start(seat.membership_id.id, other_slide.id)
        self.assertEqual(
            service._start(seat.membership_id.id, slide.id).survey_id, slide.with_user(self.author).survey_id
        )
        other_attempt = service._start(blocked.membership_id.id, other_slide.id)
        service._submit(other_attempt.id)
        self.assertEqual(blocked.membership_id.completion, 100)
        self.assertEqual(seat.membership_id.completion, 0)

    def test_native_portal_wizard_and_unmanaged_sales_remain_native(self):
        course, slide, product = self.offer()
        order, line = self.order(product)
        seat = self.seat(line)
        action = seat.action_learning_prepare_portal()
        self.assertEqual(action["res_model"], "portal.wizard")
        self.assertFalse(seat.membership_id)
        ordinary = (
            self.env["product.product"]
            .with_user(self.manager)
            .create({"name": "Fictional ordinary service", "type": "service"})
        )
        ordinary.copy()
        order, normal = self.order(ordinary)
        order.action_confirm()
        self.assertFalse(normal.learning_channel_id)
        order.write({"user_id": self.salesperson.id})
        duplicate = order.with_user(self.salesperson).copy()
        self.assertFalse(duplicate.order_line.learning_channel_id)

    def test_native_invitation_prepares_one_account_without_opening_the_course(self):
        course, slide, product = self.offer()
        order, line = self.order(product)
        beneficiary = self.env["res.partner"].create(
            {"name": "Fictional invited beneficiary", "email": "fictional-invited@example.invalid"}
        )
        seat = (
            self.env["training.elearning.sale.allocation"]
            .with_user(self.manager)
            .create({"line_id": line.id, "partner_id": beneficiary.id})
        )
        action = seat.action_learning_prepare_portal()
        wizard = self.env["portal.wizard"].with_user(self.manager).browse(action["res_id"])
        self.assertEqual(wizard.user_ids.partner_id, beneficiary)
        # Exercise native account and invitation creation; no external SMTP in tests.
        with patch.object(type(self.env["mail.mail"]), "send", return_value=True) as transport:
            wizard.user_ids.action_grant_access()
        self.assertTrue(transport.called)
        self.assertEqual(len(beneficiary.user_ids), 1)
        self.assertFalse(beneficiary.user_ids.login_date)
        self.assertFalse(seat.membership_id)
        order.action_confirm()
        line.action_learning_authorize("Fictional verified invitation purchase")
        seat.action_learning_activate()
        self.assertTrue(seat.membership_id.learning_started_at)
        self.assertFalse(beneficiary.user_ids.login_date)
