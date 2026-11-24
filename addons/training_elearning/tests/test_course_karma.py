"""Native "Course finished" karma for managed courses (gamification, 24 November 2026)."""

from uuid import uuid4

from odoo.tests import tagged

from .test_certificate import CertificateCase


@tagged("post_install", "-at_install")
class TestCourseKarma(CertificateCase):
    def karma(self):
        self.learner.invalidate_recordset(["karma"])
        return self.learner.karma

    def test_completion_earns_once_and_invalidation_withdraws(self):
        before = self.karma()
        course, slide, member = self.completed_course()
        finish = course.karma_gen_channel_finish
        self.assertEqual(self.karma(), before + finish)
        self.assertEqual(member.sudo().learning_karma_granted, finish)

        member._learning_sync_progress()
        self.assertEqual(self.karma(), before + finish, "A completed course earns its karma once.")

        self.env["training.elearning.acquisition.invalidation"].with_user(self.pedagogy)._invalidate(
            member, slide.id, "Fictional motivated acquisition decision", str(uuid4())
        )
        self.assertEqual(member.completion, 0)
        self.assertEqual(self.karma(), before)
        self.assertFalse(member.sudo().learning_karma_granted)

        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, slide.id)
        self.assertEqual(member.completion, 100)
        self.assertEqual(self.karma(), before + finish)

    def test_no_karma_when_the_course_grants_none(self):
        before = self.karma()
        course, slide = self.edition("Fictional course without karma")
        course.sudo().karma_gen_channel_finish = 0
        member = self.member(course)
        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, slide.id)
        self.assertEqual(member.completion, 100)
        self.assertEqual(self.karma(), before)

    def test_deleted_dossier_takes_its_course_karma(self):
        before = self.karma()
        _course, _slide, member = self.completed_course()
        self.assertGreater(self.karma(), before)
        member.with_user(self.manager).action_learning_revoke("Fictional end of access")
        member.with_user(self.env.ref("base.user_admin")).action_training_delete_dossier()
        self.assertFalse(member.exists())
        self.assertEqual(self.karma(), before)
