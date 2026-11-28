"""« Mes cours » : les cours autonomes actifs de la personne, et d'elle seule."""

from odoo.tests import new_test_user, tagged

from .test_activities import LessonCase


@tagged("post_install", "-at_install")
class TestMyCourses(LessonCase):
    def test_active_courses_are_contributed_to_my_courses(self):
        course = self.course()
        member = self.member(course)
        other = new_test_user(self.env, login="fictional_other_learner", groups="base.group_portal")
        contributions = self.env["training.my.courses"]
        self.assertTrue(contributions.with_user(self.learner)._has_courses())
        self.assertFalse(contributions.with_user(other)._has_courses())
        rows = contributions.with_user(self.learner)._online_rows()
        self.assertEqual([row["url"] for row in rows], ["/my/learning/%s" % member.id])
        self.assertEqual(rows[0]["name"], course.name)
        self.assertIn("access until", rows[0]["detail"])
        self.assertEqual(contributions.with_user(self.learner)._online_url(), "/my/learning")
        self.assertFalse(contributions.with_user(other)._online_rows())
