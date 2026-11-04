"""Native mail preparation, future-only scheduling and authorization at send time."""

from datetime import timedelta
from unittest.mock import patch
from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from .test_human_practical import HumanCase


@tagged("post_install", "-at_install")
class TestScopedReminders(HumanCase):
    def notices(self, member, kind=None):
        domain = [("membership_id", "=", member.id)]
        if kind:
            domain.append(("kind", "=", kind))
        return self.env["training.elearning.reminder"].sudo().search(domain)

    def test_template_reload_retains_obsolete_notifications_without_link_or_delivery(self):
        course = self.course()
        self.article(course)
        course.action_learning_publish()
        member = self.member(course)
        obsolete = self.notices(member, "activation")
        member.action_learning_activate(
            fields.Datetime.now() + timedelta(days=60), self.learner.id, "Fictional second financed grant"
        )
        self.assertFalse(obsolete._target())
        template = self.env.ref("training_elearning.scoped_reminder_template")
        # Odoo validates an existing model record when XML reloads the template.
        template.write({"body_html": template.body_html})
        body = template._render_field("body_html", obsolete.ids)[obsolete.id]
        self.assertNotIn('href=', body)
        self.assertFalse(obsolete.mail_id._learning_delivery_allowed())
        self.assertEqual(obsolete.state, "cancelled")
        current = self.notices(member, "activation") - obsolete
        self.assertEqual(len(current), 1)
        self.assertIn("/my/learning/%s" % member.id, template._render_field("body_html", current.ids)[current.id])
        self.assertTrue(current.mail_id._learning_delivery_allowed())

    def test_activation_uses_native_queue_and_live_identity_before_smtp(self):
        course = self.course()
        self.article(course)
        course.action_learning_publish()
        member = self.member(course)
        notice = self.notices(member, "activation")
        self.assertEqual(len(notice), 1)
        self.assertEqual(notice.state, "queued")
        mail = notice.mail_id
        self.assertEqual(mail.recipient_ids, self.learner.partner_id)
        self.assertFalse(mail.email_to or mail.email_cc or mail.attachment_ids)
        self.assertTrue(mail._learning_delivery_allowed())
        self.assertNotIn("PRIVATE LESSON TEXT", str(mail.body_html))
        self.learner.active = False
        self.assertFalse(mail._learning_delivery_allowed())
        self.assertEqual(notice.state, "cancelled")
        mail._send()
        self.assertEqual(mail.state, "cancel")

    def test_future_only_offsets_extension_and_changed_policy_cancel_old_mail(self):
        course = self.course()
        self.article(course)
        course.action_learning_publish()
        member = self.member(course)
        reminders = self.env["training.elearning.reminder"]
        now = fields.Datetime.now()
        self.assertFalse(reminders._enqueue("course_end", member, offset=7))
        member.action_learning_activate(now + timedelta(days=60), self.learner.id, "Fictional longer access")
        early = reminders._enqueue("course_end", member, offset=30)
        short = reminders._enqueue("course_end", member, offset=7)
        self.assertEqual(early.state, "pending")
        self.assertEqual(reminders._enqueue("course_end", member, offset=30), early)
        with patch.object(fields.Datetime, "now", return_value=early.due_at):
            early._process()
        self.assertEqual(early.state, "queued")
        member.action_learning_activate(now + timedelta(days=90), self.learner.id, "Fictional later extension")
        self.assertFalse(early.mail_id._learning_delivery_allowed())
        short._process()
        self.assertEqual(short.state, "cancelled")
        future = reminders._enqueue("course_end", member, offset=7)
        course.learning_company_id.with_user(self.env.ref("base.user_admin")).learning_notice_short_days = 5
        future._process()
        self.assertEqual(future.state, "cancelled")
        self.assertFalse(reminders._enqueue("course_end", member, offset=7)._allowed())
        self.assertTrue(reminders._enqueue("course_end", member, offset=5)._allowed())

    def test_working_day_warning_and_single_future_overdue_alert(self):
        _course, slide, _task, member = self.human()
        row = self.deposit(member, slide)
        queue = row.review_queue_id
        reminders = self.env["training.elearning.reminder"]
        reminders._scan_sources()
        warning = self.notices(member, "review_due")
        late = self.notices(member, "review_late")
        self.assertEqual(len(warning), 1)
        self.assertTrue(late)
        self.assertEqual(warning.user_id, self.reviewer)
        self.assertLess(warning.due_at, queue.due_at)
        self.assertLess(warning.due_at.weekday(), 5)
        self.assertEqual(late.mapped("state"), ["pending"] * len(late))
        count = len(late)
        with patch.object(fields.Datetime, "now", return_value=queue.due_at + timedelta(seconds=1)):
            late._process()
            reminders._scan_sources()
            self.assertEqual(len(self.notices(member, "review_late")), count)
        self.assertEqual(late.mapped("state"), ["queued"] * count)
        self.publish(queue, outcome="validated", passed=True)
        self.assertFalse(warning._allowed())
        self.assertFalse(late.mail_id[0]._learning_delivery_allowed())

    def test_notification_records_and_envelope_cannot_bypass_private_boundary(self):
        course = self.course()
        self.article(course)
        course.action_learning_publish()
        notice = self.notices(self.member(course), "activation")
        notice.mail_id.email_to = "fictional-unrelated@example.invalid"
        self.assertFalse(notice.mail_id._learning_delivery_allowed())
        with self.assertRaises(AccessError):
            notice.with_user(self.learner).read(["event_key"])
        with self.assertRaises(AccessError):
            notice.write({"user_id": self.other.id})
        with self.assertRaises(AccessError):
            self.env["ir.attachment"].create(
                {
                    "name": "Fictional forbidden notification file",
                    "res_model": notice._name,
                    "res_id": notice.id,
                    "type": "url",
                    "url": "https://example.invalid/private",
                }
            )
