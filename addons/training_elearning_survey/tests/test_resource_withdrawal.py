"""A standard archive cannot bypass the motivated closure of engaged exam activities."""

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged, new_test_user
from .test_autonomous import AutonomousCase


@tagged("post_install", "-at_install")
class TestEngagedExamArchive(AutonomousCase):
    def test_archive_requires_context_closure_and_preserves_interrupted_answers(self):
        course, slide = self.offer(obligations=["complete"])
        member = self.member(course)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slide.id)
        question = attempt.predefined_question_ids[0]
        service._save(attempt.id, question.id, question.suggested_answer_ids.filtered("is_correct").ids, True)
        answers = attempt.user_input_line_ids.read(["id", "question_id", "suggested_answer_id", "answer_score"])
        with self.assertRaises(ValidationError):
            slide.survey_id.with_user(self.manager).write({"active": False})
        self.assertTrue(slide.survey_id.active)
        slide.with_user(self.manager).action_learning_change_availability("Fictional motivated exam closure")
        self.assertTrue(attempt.learning_interrupted_at)
        slide.survey_id.with_user(self.manager).write({"active": False})
        self.assertEqual(
            attempt.user_input_line_ids.read(["id", "question_id", "suggested_answer_id", "answer_score"]), answers
        )
        self.assertEqual(member.completion, 0)
        with self.assertRaises(AccessError):
            service._result(attempt)

    def test_unmanaged_native_survey_archive_keeps_standard_permissions(self):
        author = new_test_user(
            self.env, login="fictional_standard_survey_archiver", groups="base.group_user,survey.group_survey_user"
        )
        survey = self.env["survey.survey"].with_user(author).create({"title": "Fictional ordinary native survey"})
        survey.write({"active": False})
        self.assertFalse(survey.active)
