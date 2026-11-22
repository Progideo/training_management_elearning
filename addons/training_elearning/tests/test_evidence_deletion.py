from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .test_practical import PracticalCase


@tagged("post_install", "-at_install")
class TestEvidenceDeletion(PracticalCase):
    """Conservation configurée (22 November 2026): learner evidence stays by default; only
    an administrator, by hand or through a rule he configured, deletes it."""

    def learner_dossier(self):
        course = self.course()
        deposit, _task = self.task(course)
        course.action_learning_publish()
        member = self.member(course)
        submission = self.deposit(member, deposit)
        self.assertTrue(submission)
        return member, submission

    def test_only_an_administrator_deletes_evidence(self):
        member, _submission = self.learner_dossier()
        reminders = self.env["training.elearning.reminder"].sudo().search([("membership_id", "=", member.id)])
        self.assertTrue(reminders)
        for user in (self.manager, self.learner):
            # sudo() alone never authorizes: the real user decides.
            with self.assertRaises((AccessError, ValidationError)):
                reminders.with_user(user).sudo().unlink()
        reminders.with_user(self.env.ref("base.user_admin")).sudo().unlink()
        self.assertFalse(reminders.exists())

    def test_finished_learner_dossier_is_deleted_with_its_evidence(self):
        member, submission = self.learner_dossier()
        admin = self.env.ref("base.user_admin")
        with self.assertRaises(AccessError):
            member.with_user(self.manager).action_training_delete_dossier()
        with self.assertRaisesRegex(ValidationError, "finished or cancelled"):
            member.with_user(admin).action_training_delete_dossier()
        member.with_user(self.manager).action_learning_revoke("Fictional end of access")
        member.with_user(admin).action_training_delete_dossier()
        self.assertFalse(member.exists())
        self.assertFalse(submission.exists())
