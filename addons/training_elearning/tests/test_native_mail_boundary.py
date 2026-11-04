"""Native activity messages do not bypass private delivery-evidence projections."""

from odoo import Command
from odoo.tests import tagged
from .test_human_practical import HumanCase


@tagged("post_install", "-at_install")
class TestNativeLearningMailBoundary(HumanCase):
    def test_activity_role_is_rechecked_without_blocking_unrelated_native_mail(self):
        _course, slide, _task, member = self.human()
        row = self.deposit(member, slide)
        queue = row.review_queue_id
        native = self.env["mail.mail"].create(
            {
                "subject": "Fictional native activity",
                "body_html": "<p>Fictional pending correction activity</p>",
                "model": queue._name,
                "res_id": queue.id,
                "recipient_ids": [Command.set(self.reviewer.partner_id.ids)],
            }
        )
        self.assertTrue(native._learning_delivery_allowed())
        self.reviewer.write(
            {"group_ids": [Command.unlink(self.env.ref("training_elearning.group_elearning_reviewer").id)]}
        )
        self.assertFalse(self.reviewer.has_group("training_elearning.group_elearning_reviewer"))
        self.assertFalse(native._learning_delivery_allowed())
        other = self.env["mail.mail"].create(
            {
                "subject": "Fictional ordinary native message",
                "body_html": "<p>Fictional ordinary content</p>",
                "model": "res.partner",
                "res_id": self.other.partner_id.id,
                "email_to": "fictional-ordinary@example.invalid",
            }
        )
        self.assertTrue(other._learning_delivery_allowed())

    def test_internal_evidence_notice_is_not_exposed_via_untracked_chatter(self):
        _course, slide, _task, member = self.human()
        row = self.deposit(member, slide)
        notice = row.review_queue_id.assignment_notice_id
        native = self.env["mail.mail"].create(
            {
                "subject": "Fictional private activity",
                "body_html": "<p>Fictional internal metadata</p>",
                "model": notice._name,
                "res_id": notice.id,
                "recipient_ids": [Command.set(self.learner.partner_id.ids)],
            }
        )
        self.assertFalse(native._learning_delivery_allowed())
        self.assertTrue(notice.mail_id._learning_delivery_allowed())
