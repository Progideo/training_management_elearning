"""Motivated closures, immutable acquisitions and recipient recheck at native send."""

from unittest.mock import patch
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged, new_test_user
from .test_activities import LessonCase


@tagged("post_install", "-at_install")
class TestActivityAvailability(LessonCase):
    def test_closure_preserves_acquisition_and_replays_do_not_duplicate_notices(self):
        course = self.course()
        article = self.article(course)
        pdf = self.pdf(course)
        course.action_learning_publish()
        member = self.member(course)
        service = self.env["training.elearning.service"].with_user(self.learner)
        service._declare(member.id, article.id)
        end = member.learning_ends_at
        pdf.action_learning_change_availability("Fictional temporary rights review")
        self.assertEqual(member.completion, 50)
        self.assertEqual(member.learning_ends_at, end)
        self.assertFalse(service._item_status(member, pdf._learning_plan_item())["complete"])
        self.assertTrue(service._item_status(member, pdf._learning_plan_item())["unavailable"])
        with self.assertRaises(AccessError):
            service._declare(member.id, pdf.id)
        with self.assertRaises(ValidationError):
            pdf.write({"active": False})
        notices = (
            self.env["training.elearning.notice"]
            .sudo()
            .search([("membership_id", "=", member.id), ("slide_id", "=", pdf.id)])
        )
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices.state, "queued")
        self.assertTrue(notices.mail_id)
        self.assertNotIn("PRIVATE LESSON TEXT", notices.mail_id.body_html)
        self.assertFalse(notices.mail_id.attachment_ids)
        pdf.action_learning_change_availability("Fictional repeated close")
        self.assertEqual(len(pdf.learning_availability_log), 1)
        self.assertEqual(
            self.env["training.elearning.notice"]
            .sudo()
            .search_count([("membership_id", "=", member.id), ("slide_id", "=", pdf.id)]),
            1,
        )
        pdf.action_learning_change_availability("Fictional issue resolved", reopen=True)
        service._declare(member.id, pdf.id)
        self.assertEqual(member.completion, 100)
        acquired = member.completion_date
        article.action_learning_change_availability("Fictional later resource closure")
        self.assertEqual(member.completion, 100)
        self.assertEqual(member.completion_date, acquired)
        self.assertTrue(member._learning_progress()["complete"])
        pdf.action_learning_change_availability("Fictional second independent closure")
        # Even the same closed state has a new epoch; the old queued notice is stale.
        notices.mail_id._send()
        self.assertEqual(notices.state, "cancelled")
        self.assertEqual(notices.mail_id.state, "cancel")

    def test_live_account_revocation_cancels_before_native_transport_and_keeps_unrelated_mail(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        member = self.member(course)
        slide.action_learning_change_availability("Fictional account notification scope")
        notice = self.env["training.elearning.notice"].sudo().search([("membership_id", "=", member.id)])
        self.assertEqual(notice.state, "queued")
        self.learner.sudo().write({"active": False})
        notice.mail_id._send()
        self.assertEqual(notice.state, "cancelled")
        self.assertEqual(notice.mail_id.state, "cancel")
        unrelated = self.env["mail.mail"].create(
            {
                "subject": "Fictional ordinary mail",
                "body_html": "<p>Fictional unrelated message</p>",
                "email_to": "fictional@example.invalid",
            }
        )
        unrelated._send()  # Native Odoo test mode disables actual transport.
        self.assertEqual(unrelated.state, "outgoing")

    def test_delivery_incident_is_recorded_once_and_retry_reuses_native_mail(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        member = self.member(course)
        slide.action_learning_change_availability("Fictional delivery incident")
        notice = self.env["training.elearning.notice"].sudo().search([("membership_id", "=", member.id)])
        mail = notice.mail_id
        mail.write({"state": "exception", "failure_reason": "Fictional confined delivery failure"})
        notice._sync()
        notice._sync()
        self.assertEqual(notice.state, "exception")
        self.assertTrue(notice.incident_activity_id)
        activity = notice.incident_activity_id
        self.assertEqual(activity.user_id, self.manager)
        notice.with_user(self.manager).action_retry()
        self.assertEqual(notice.mail_id, mail)
        self.assertEqual(mail.state, "outgoing")
        self.assertEqual(notice.state, "queued")
        self.assertEqual(notice.incident_activity_id, activity)
        self.learner.sudo().write({"active": False})
        mail._send()
        self.assertEqual(notice.state, "cancelled")

    def test_queue_preparation_failure_keeps_closure_and_records_coordinator_incident(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        member = self.member(course)
        template = self.env.ref("training_elearning.activity_notice")
        with patch.object(type(template), "send_mail", side_effect=RuntimeError("Fictional confined queue failure")):
            slide.action_learning_change_availability("Fictional availability decision despite mail incident")
        self.assertTrue(slide.learning_withdrawn_at)
        notice = self.env["training.elearning.notice"].sudo().search([("membership_id", "=", member.id)])
        self.assertEqual(notice.state, "exception")
        self.assertFalse(notice.mail_id)
        self.assertTrue(notice.incident_activity_id)
        notice.with_user(self.manager).action_retry()
        self.assertEqual(notice.state, "queued")
        self.assertTrue(notice.mail_id)
        self.assertTrue(slide.learning_withdrawn_at)

    def test_author_learner_and_forged_audit_cannot_close_or_explore_notices(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        member = self.member(course)
        author = new_test_user(
            self.env, login="fictional_availability_author", groups="training_elearning.group_elearning_author"
        )
        for user in (author, self.learner):
            with self.assertRaises(AccessError):
                slide.with_user(user).action_learning_change_availability("Fictional unprivileged closure")
            with self.assertRaises(AccessError):
                self.env["training.elearning.notice"].with_user(user).search([])
        with self.assertRaises(ValidationError):
            slide.action_learning_change_availability(" ")
        for field in ("learning_withdrawn_at", "learning_availability_event", "learning_availability_log"):
            with self.assertRaises(AccessError):
                slide.write({field: False})
        slide.action_learning_change_availability("Fictional authorized close")
        notice = self.env["training.elearning.notice"].sudo().search([("membership_id", "=", member.id)])
        with self.assertRaises(AccessError):
            notice.write({"state": "sent"})
        with self.assertRaises(AccessError):
            notice.unlink()
