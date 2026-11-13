"""Invalidated native exam evidence cannot be silently projected again."""

from uuid import uuid4
from odoo.tests import tagged, new_test_user
from .test_autonomous import AutonomousCase


@tagged("post_install", "-at_install")
class TestExamAcquisitionInvalidation(AutonomousCase):
    def test_old_pass_is_barred_and_new_revision_is_explicit_new_proof(self):
        course, slide = self.offer()
        member = self.member(course)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slide.id)
        question = attempt.predefined_question_ids[0]
        service._save(attempt.id, question.id, question.suggested_answer_ids.filtered("is_correct").ids, True)
        service._submit(attempt.id)
        self.assertEqual(member.completion, 100)
        answers = attempt.user_input_line_ids.read(["question_id", "suggested_answer_id", "answer_score"])
        pedagogy = new_test_user(
            self.env,
            login="fictional_exam_invalidation_pedagogy",
            groups="training_elearning.group_elearning_pedagogy_manager",
        )
        event = (
            self.env["training.elearning.acquisition.invalidation"]
            .with_user(pedagogy)
            ._invalidate(member, slide.id, "Fictional explicit exam invalidation", str(uuid4()))
        )
        for _repeat in range(2):
            member._learning_sync_progress()
            self.assertEqual(member.completion, 0)
        self.assertFalse(service._requirement_status(service._requirement(member, slide.id))["satisfied"])
        evidence = self.env["training.elearning.service"]._period_result_evidence(
            member,
            member._learning_plan()["slides"][0],
            attempt.end_datetime.replace(year=attempt.end_datetime.year + 1),
        )
        self.assertFalse(evidence["complete"])
        self.env["training.exam.revision"].with_user(self.manager)._record(
            attempt,
            {str(question.id): 2},
            "Fictional new motivated review",
            request_key=str(uuid4()),
            expected_previous=0,
        )
        self.assertEqual(member.completion, 100)
        self.assertTrue(event.restored_at)
        self.assertEqual(
            attempt.user_input_line_ids.read(["question_id", "suggested_answer_id", "answer_score"]), answers
        )
