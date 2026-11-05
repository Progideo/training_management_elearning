"""Actual human queue permissions, rubric publication and targeted late revisions."""

from datetime import timedelta
from unittest.mock import patch
from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, Form, new_test_user, tagged
from .test_practical import PracticalCase


class HumanCase(PracticalCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reviewer = new_test_user(
            cls.env, login="fictional_practical_reviewer", groups="training_elearning.group_elearning_reviewer"
        )
        cls.reviewer2 = new_test_user(
            cls.env, login="fictional_practical_reviewer_second", groups="training_elearning.group_elearning_reviewer"
        )

    def human(self, with_pdf=False):
        course = self.course()
        course.with_user(self.pedagogy).write({"learning_reviewer_id": self.reviewer.id})
        task = (
            self.env["training.elearning.practical"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional human practical",
                    "training_course_id": self.catalog.id,
                    "criterion": "human",
                    "instructions": "PRIVATE HUMAN PRACTICAL INSTRUCTIONS",
                    "rubric_ids": [Command.create({"description": "Fictional required criterion"})],
                }
            )
        )
        task.action_publish()
        slide = (
            self.env["slide.slide"]
            .with_user(self.manager)
            .create(
                {
                    "channel_id": course.id,
                    "learning_practical_id": task.id,
                    "is_published": True,
                }
            )
        )
        if with_pdf:
            self.pdf(course).write({"learning_optional": True})
        course.action_learning_publish()
        member = self.member(course)
        return course, slide, task, member

    def publish(self, queue, *, outcome="revision", passed=False, user=None):
        return queue.with_user(user or self.reviewer)._publish(
            queue.submission_id.id,
            outcome,
            {str(line.id): passed for line in queue.practical_id.rubric_ids},
            "PRIVATE FICTIONAL HUMAN FEEDBACK",
        )

    def sent(self, notice):
        # Native Odoo test mode disables SMTP. Exercise the real queue-state
        # observation using a confined, synthetic native delivery transition.
        notice.mail_id.sudo().write({"state": "sent"})
        notice._sync()
        self.assertEqual(notice.state, "sent")


@tagged("post_install", "-at_install")
class TestHumanPractical(HumanCase):
    def test_latest_pending_keeps_first_receipt_deadline_and_stale_form_cannot_grade(self):
        _course, slide, task, member = self.human()
        first = self.deposit(member, slide)
        queue = first.review_queue_id
        first_at, due = queue.first_received_at, queue.due_at
        self.assertEqual(queue.reviewer_id, self.reviewer)
        self.assertEqual(member.completion, 0)
        self.assertEqual(member._learning_progress()["satisfied"], 0)
        later = fields.Datetime.now() + timedelta(hours=2)
        with patch.object(fields.Datetime, "now", return_value=later):
            second = self.deposit(member, slide)
        self.assertEqual(queue.submission_id, second)
        self.assertEqual(queue.first_received_at, first_at)
        self.assertEqual(queue.due_at, due)
        self.assertEqual(first.payload_id.file_ids.raw.content, b"PRIVATE FICTIONAL SUBMISSION")
        with self.assertRaises(ValidationError):
            queue.with_user(self.reviewer)._publish(
                first.id, "validated", {str(task.rubric_ids.id): True}, "Stale feedback"
            )
        with self.assertRaises(ValidationError):
            self.publish(queue, outcome="validated", passed=False)
        with self.assertRaises(AccessError):
            self.publish(queue, outcome="validated", passed=True, user=self.pedagogy)
        with Form(
            self.env["training.elearning.review.wizard"]
            .with_user(self.reviewer)
            .with_context(default_queue_id=queue.id)
        ) as form:
            with form.line_ids.edit(0) as criterion:
                criterion.satisfied = True
            form.outcome = "validated"
            form.feedback = "PRIVATE FICTIONAL FORM FEEDBACK"
        form.record.action_publish()
        review = second.review_id
        self.assertEqual(review.outcome, "validated")
        self.assertEqual(member.completion, 100)
        self.assertTrue(member.completion_date)
        self.assertEqual(self.publish(queue, outcome="validated", passed=True), review)
        acquired = member.completion_date
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.now() + timedelta(hours=1)):
            third = self.deposit(member, slide)
            self.publish(queue, outcome="revision", passed=False)
        self.assertNotEqual(third, second)
        self.assertEqual(second.review_id, review)
        self.assertEqual(member.completion, 100)
        self.assertEqual(member.completion_date, acquired)

        with self.assertRaises(AccessError):
            review.with_user(self.reviewer).write({"feedback": "Changed"})
        with self.assertRaises(ValidationError):
            task.rubric_ids.write({"description": "Changed published rubric"})

    def test_reassignment_revokes_files_without_changing_deadline_or_history(self):
        _course, slide, _task, member = self.human()
        row = self.deposit(member, slide)
        queue = row.review_queue_id
        due = queue.due_at
        self.reviewer.active = False
        with self.assertRaises(AccessError):
            self.env["training.elearning.practical.service"].with_user(self.learner)._context(member.id, slide.id)
        self.reviewer.active = True
        row.payload_id.with_user(self.reviewer)._authorize_staff()
        self.assertTrue(row.payload_id.with_user(self.reviewer).read(["file_evidence"]))
        old_notice = queue.assignment_notice_id
        with self.assertRaises(AccessError):
            old_notice.mail_id.with_user(self.reviewer).write({"state": "sent"})

        queue.with_user(self.pedagogy)._reassign(self.reviewer2, "Fictional replacement reviewer")
        self.assertEqual(queue.due_at, due)
        self.assertTrue(queue.assignment_log)
        with self.assertRaises(AccessError):
            row.payload_id.with_user(self.reviewer)._authorize_staff()
        with self.assertRaises(AccessError):
            row.payload_id.with_user(self.reviewer).read(["file_evidence"])
        with self.assertRaises(AccessError):
            self.publish(queue)
        row.payload_id.with_user(self.reviewer2)._authorize_staff()
        old_notice.mail_id._send()
        self.assertEqual(old_notice.state, "cancelled")
        self.assertEqual(old_notice.mail_id.state, "cancel")
        self.publish(queue, outcome="validated", passed=True, user=self.reviewer2)
        self.assertEqual(member.completion, 100)

    def test_other_operating_company_cannot_read_or_receive_assignment(self):
        _course, slide, _task, member = self.human()
        row = self.deposit(member, slide)
        foreign = self.env["res.company"].create({"name": "Fictional other review operator"})
        outsider = new_test_user(
            self.env,
            login="fictional_foreign_practical_coordinator",
            groups="training_elearning.group_elearning_pedagogy_manager",
            company_id=foreign.id,
            company_ids=[Command.set(foreign.ids)],
        )
        with self.assertRaises(AccessError):
            row.review_queue_id.with_user(outsider).read(["learner_name"])
        with self.assertRaises(AccessError):
            row.payload_id.with_user(outsider)._authorize_staff()
        with self.assertRaises(ValidationError):
            row.review_queue_id.with_user(self.pedagogy)._reassign(outsider, "Fictional cross-company attempt")

    def test_late_feedback_needs_delivery_and_late_validation_completes_native_course(self):
        course, slide, _task, member = self.human()
        row = self.deposit(member, slide)
        queue = row.review_queue_id
        late = member.learning_ends_at + timedelta(hours=1)
        service = self.env["training.elearning.practical.service"].with_user(self.learner)
        with patch.object(fields.Datetime, "now", return_value=late):
            review = self.publish(queue)
            self.assertFalse(queue.revision_until)
            for actor in (self.reviewer, self.learner):
                with self.assertRaises(AccessError):
                    review.delivery_notice_id.mail_id.with_user(actor).write({"state": "sent"})
            with self.assertRaises(AccessError):
                service._context(member.id, slide.id)
            self.sent(review.delivery_notice_id)
            self.assertEqual(queue.revision_until, late + timedelta(days=14))
            service._context(member.id, slide.id)
            with self.assertRaises(AccessError):
                self.env["training.elearning.service"].with_user(self.learner)._activity(member.id, slide.id)
            next_row = self.deposit(member, slide)
            self.assertTrue(queue.late_submission_used)
            with self.assertRaises(AccessError):
                self.deposit(member, slide)
            self.assertEqual(row.review_id, review)
            self.assertNotEqual(next_row, row)
            final = self.publish(queue, outcome="validated", passed=True)
            self.assertEqual(final.submission_id, next_row)
            self.assertEqual(member.completion, 100)
            self.assertEqual(member.member_status, "completed")
            self.assertEqual(member.completion_date, late)
            self.assertEqual(service._history(row.id), row.sudo())
        self.assertTrue(course.learning_review_calendar_id.learning_review_snapshot)

    def test_bounce_blocks_closure_and_resolution_restores_full_window(self):
        _course, slide, _task, member = self.human()
        queue = self.deposit(member, slide).review_queue_id
        late = member.learning_ends_at + timedelta(hours=1)
        with patch.object(fields.Datetime, "now", return_value=late):
            review = self.publish(queue)
            notice = review.delivery_notice_id
            notice.mail_id.write({"state": "exception", "failure_reason": "Fictional immediate failure"})
            notice._sync()
            self.assertFalse(queue._revision_open())
            self.assertFalse(queue.revision_until)
            self.assertTrue(notice.incident_activity_id)
            with Form(
                self.env["training.elearning.review.delivery"]
                .with_user(self.pedagogy)
                .with_context(default_notice_id=notice.id)
            ) as form:
                form.reason = "Fictional repaired address"
            action = form.record.action_apply()
            self.assertEqual(action["type"], "ir.actions.act_window")
            self.assertEqual(action["res_model"], "training.elearning.review.notice")
            self.assertEqual(action["target"], "current")
            new = self.env["training.elearning.review.notice"].browse(action["res_id"])
            self.assertEqual(new, review.delivery_notice_id)
            self.assertEqual(new.attempt, notice.attempt + 1)
            self.sent(new)
            self.assertEqual(queue.revision_until, late + timedelta(days=14))
            notification = self.env["mail.notification"].create(
                {
                    "mail_message_id": new.mail_id.mail_message_id.id,
                    "mail_mail_id": new.mail_id.id,
                    "res_partner_id": self.learner.partner_id.id,
                    "notification_type": "email",
                    "notification_status": "sent",
                }
            )
        after = late + timedelta(days=15)
        with patch.object(fields.Datetime, "now", return_value=after):
            self.env["training.elearning.review.queue"]._cron_review_closure()
            self.assertEqual(queue.state, "closed")
            notification.write({"notification_status": "bounce", "failure_type": "mail_bounce"})
            self.assertEqual(new.state, "exception")
            self.assertEqual(queue.state, "revision")
            self.assertFalse(queue._revision_open())
            self.env["training.elearning.review.queue"]._cron_review_closure()
            self.assertEqual(queue.state, "revision")
            manual_id = new.with_user(self.pedagogy).action_retry(
                reason="Fictional agreed phone delivery completed", manual=True
            )
            manual = self.env["training.elearning.review.notice"].browse(manual_id)
            self.assertTrue(manual.manual_delivery)
            self.assertEqual(queue.revision_until, after + timedelta(days=14))
            self.assertTrue(queue._revision_open())

    def test_feedback_mail_is_private_and_rechecks_actual_recipient_before_transport(self):
        _course, slide, _task, member = self.human()
        queue = self.deposit(member, slide).review_queue_id
        template = self.env.ref("training_elearning.practical_feedback_notice")
        template.write({"email_to": "fictional-unrelated@example.invalid", "email_cc": "fictional-cc@example.invalid"})
        review = self.publish(queue)
        notice = review.delivery_notice_id
        self.assertEqual(notice.mail_id.recipient_ids, self.learner.partner_id)
        self.assertFalse(notice.mail_id.email_to)
        self.assertFalse(notice.mail_id.email_cc)
        self.assertFalse(notice.mail_id.attachment_ids)
        notice.mail_id.write({"recipient_ids": [Command.set(self.other.partner_id.ids)]})
        notice.mail_id._send()
        self.assertEqual(notice.state, "cancelled")
        self.assertEqual(notice.mail_id.state, "cancel")
        self.assertFalse(queue.revision_until)

    def test_one_late_revision_does_not_grant_another_after_nonvalidation(self):
        _course, slide, _task, member = self.human()
        queue = self.deposit(member, slide).review_queue_id
        late = member.learning_ends_at + timedelta(hours=1)
        with patch.object(fields.Datetime, "now", return_value=late):
            first = self.publish(queue)
            self.sent(first.delivery_notice_id)
            self.deposit(member, slide)
            final = self.publish(queue)
            self.assertFalse(final.revision_eligible)
            self.sent(final.delivery_notice_id)
            self.assertEqual(queue.state, "closed")
            self.assertEqual(member.completion, 0)
            with self.assertRaises(AccessError):
                self.deposit(member, slide)

    def test_inactive_or_self_reviewer_never_opens_human_practical(self):
        _course, slide, _task, member = self.human()
        self.reviewer.active = False
        service = self.env["training.elearning.practical.service"].with_user(self.learner)
        with self.assertRaises(AccessError):
            service._context(member.id, slide.id)
        with self.assertRaises(AccessError):
            self.deposit(member, slide)
        self.assertFalse(self.env["training.elearning.submission"].search([("membership_id", "=", member.id)]))
        with self.assertRaises(AccessError):
            self.env["training.elearning.review"].with_user(self.learner).create({"feedback": "Forged judgement"})


@tagged("post_install", "-at_install")
class TestHumanPracticalPortal(HumanCase, HttpCase):
    def test_targeted_revision_page_and_files_do_not_reopen_pdf_or_other_learners(self):
        course, slide, _task, member = self.human(with_pdf=True)
        pdf = course.slide_ids.filtered(lambda item: item.slide_category == "document")
        row = self.deposit(member, slide)
        queue = row.review_queue_id
        late = member.learning_ends_at + timedelta(hours=1)
        with patch.object(fields.Datetime, "now", return_value=late):
            review = self.publish(queue)
            self.sent(review.delivery_notice_id)
            self.authenticate(self.learner.login, self.learner.login)
            path = f"/my/learning/{member.id}/tasks/{slide.id}"
            page = self.url_open(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn("PRIVATE HUMAN PRACTICAL INSTRUCTIONS", page.text)
            history = self.url_open(f"/my/learning-submissions/{row.id}")
            self.assertEqual(history.status_code, 200)
            self.assertIn("PRIVATE FICTIONAL HUMAN FEEDBACK", history.text)
            self.assertNotIn("PRIVATE FICTIONAL HUMAN FEEDBACK", self.url_open(f"/my/learning/{member.id}").text)
            self.assertEqual(self.url_open(f"/my/learning/{member.id}/activities/{slide.id}").status_code, 404)
            self.assertEqual(self.url_open(f"/my/learning/{member.id}/activities/{pdf.id}/pdf").status_code, 404)
            import re

            csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
            key = re.search(r'name="request_key" value="([^"]+)"', page.text)[1]
            response = self.url_open(
                path + "/deposit",
                data={"csrf_token": csrf, "request_key": key},
                files={"files": ("fictional-revision.txt", b"PRIVATE TARGETED REVISION", "text/plain")},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("Mon rendu conservé", response.text)
            self.assertTrue(queue.late_submission_used)
            self.assertEqual(queue.submission_id.payload_id.file_ids.raw.content, b"PRIVATE TARGETED REVISION")
            self.authenticate(self.reviewer.login, self.reviewer.login)
            file = row.payload_id.file_ids
            self.assertEqual(self.url_open(f"/web/content/{file.id}").content, b"PRIVATE FICTIONAL SUBMISSION")
            queue.with_user(self.pedagogy)._reassign(self.reviewer2, "Fictional portal privacy recheck")
            response = self.url_open(f"/web/content/{file.id}")
            self.assertIn(response.status_code, (403, 404))
            self.assertNotIn(b"PRIVATE FICTIONAL SUBMISSION", response.content)
            self.authenticate(self.other.login, self.other.login)
            self.assertEqual(self.url_open(path).status_code, 404)
            self.assertEqual(self.url_open(f"/my/learning-submissions/{row.id}").status_code, 404)
        self.assertTrue(course.learning_bound_at)
