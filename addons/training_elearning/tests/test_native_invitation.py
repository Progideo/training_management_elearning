"""Native account invitations also work without the Sales or Survey integrations."""

from datetime import timedelta
from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from .test_path import PathCase


@tagged("post_install", "-at_install")
class TestNativeLearningInvitations(PathCase):
    def beneficiary(self, email):
        return self.env["res.partner"].create({"name": "Fictional direct invitation beneficiary", "email": email})

    def test_direct_native_membership_prepares_own_credentials_without_sales(self):
        course, _slide = self.edition("Fictional direct invitation edition")
        contact = self.beneficiary("fictional.direct.native@example.invalid")
        member = (
            self.env["slide.channel.partner"]
            .with_user(self.manager)
            .create({"channel_id": course.id, "partner_id": contact.id})
        )
        member.action_learning_activate(
            fields.Datetime.now() + timedelta(days=2), reason="Fictional controlled direct invitation"
        )
        user = contact.user_ids
        self.assertEqual(len(user), 1)
        self.assertTrue(user.has_group("base.group_portal"))
        self.assertFalse(user.has_group("base.group_user"))
        self.assertEqual(member.learning_user_id, user)
        notice = (
            self.env["training.elearning.reminder"]
            .sudo()
            .search([("membership_id", "=", member.id), ("kind", "=", "invitation")])
        )
        self.assertEqual(notice.state, "queued")
        self.assertTrue(notice.mail_id._learning_delivery_allowed())
        self.assertEqual(notice.mail_id.recipient_ids, contact)
        member.action_learning_activate(member.learning_ends_at, user.id, "Fictional explicit same-account access")
        self.assertEqual(
            len(
                self.env["training.elearning.reminder"]
                .sudo()
                .search([("membership_id", "=", member.id), ("kind", "=", "invitation")])
            ),
            1,
        )

    def test_curriculum_invitation_and_rejected_grant_are_atomic(self):
        course, _slide = self.edition("Fictional invited curriculum edition")
        path = self.path([(course, True)])
        contact = self.beneficiary("fictional.path.native@example.invalid")
        activation = (
            self.env["training.elearning.path.activation"]
            .with_user(self.manager)
            ._activate(path, contact, path._plan(), 6, 12, "Fictional controlled native curriculum invitation")
        )
        self.assertEqual(activation.registration_id.user_id, contact.user_ids)
        notice = (
            self.env["training.elearning.reminder"]
            .sudo()
            .search([("activation_id", "=", activation.id), ("kind", "=", "invitation")])
        )
        self.assertEqual(notice.state, "queued")
        self.assertTrue(notice.mail_id._learning_delivery_allowed())
        rejected = self.beneficiary("fictional.rejected.native@example.invalid")
        member = (
            self.env["slide.channel.partner"]
            .with_user(self.manager)
            .create({"channel_id": course.id, "partner_id": rejected.id})
        )
        try:
            member.action_learning_activate(
                fields.Datetime.now() - timedelta(days=1), reason="Fictional invalid deadline"
            )
        except ValidationError:  # pylint: disable=except-pass
            pass  # Production savepoint must undo the native account and queued invitation.
        else:
            self.fail("An expired proposed grant was accepted")
        self.assertFalse(rejected.user_ids)
        self.assertFalse(member.learning_started_at)
        self.assertFalse(self.env["training.elearning.reminder"].sudo().search([("partner_id", "=", rejected.id)]))
