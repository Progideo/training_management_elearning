"""Real contextual inputs interrupted by the institution never create a failed result."""

from datetime import timedelta
from unittest.mock import patch
from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from .test_autonomous import AutonomousCase


@tagged("post_install", "-at_install")
class TestExamAvailability(AutonomousCase):
    def test_interrupted_input_keeps_answers_and_clock_without_satisfying_required_completion(self):
        course, slide = self.offer(obligations=["complete"])
        member = self.member(course)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slide.id)
        question = attempt.predefined_question_ids[0]
        service._save(attempt.id, question.id, question.suggested_answer_ids.filtered("is_correct").ids, True)
        lines, deadline = attempt.user_input_line_ids, attempt.deadline
        slide.with_user(self.manager).action_learning_change_availability("Fictional institution interruption")
        self.assertEqual(attempt.state, "done")
        self.assertTrue(attempt.learning_interrupted_at)
        self.assertEqual(attempt.user_input_line_ids, lines)
        self.assertEqual(attempt.deadline, deadline)
        self.assertLess(attempt.end_datetime, deadline)
        self.assertEqual(member.completion, 0)
        stats = attempt.survey_id.sudo()
        stats.invalidate_recordset(["answer_count", "answer_done_count", "success_count"])
        self.assertEqual(stats.answer_done_count, 0)
        self.assertEqual(stats.success_count, 0)
        self.assertEqual(self.env["survey.user_input"].sudo().search_count([("id", "=", attempt.id)]), 1)
        self.assertFalse(member._learning_progress()["complete"])
        with self.assertRaises(AccessError):
            service._start(member.id, slide.id)
        with self.assertRaises(AccessError):
            service._result(attempt)
        slide.with_user(self.manager).action_learning_change_availability("Fictional resource restored", reopen=True)
        with self.assertRaises(AccessError):
            service._result(attempt)
        fresh = service._start(member.id, slide.id)
        self.assertNotEqual(fresh, attempt)
        self.assertFalse(fresh.user_input_line_ids)
        self.assertEqual(attempt.deadline, deadline)
        service._submit(fresh.id)
        self.assertEqual(member.completion, 100)

    def test_prior_success_is_kept_and_other_offer_is_not_interrupted(self):
        exam = self.exam()
        course, slide = self.offer([exam])
        other_course, other_slide = self.offer([exam])
        member, other_member = self.member(course), self.member(other_course)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        passed = service._start(member.id, slide.id)
        question = passed.predefined_question_ids[0]
        service._save(passed.id, question.id, question.suggested_answer_ids.filtered("is_correct").ids, False)
        service._submit(passed.id)
        acquired_at = member.completion_date
        pending = service._start(member.id, slide.id)
        separate = service._start(other_member.id, other_slide.id)
        slide.with_user(self.manager).action_learning_change_availability("Fictional scoped activity closure")
        self.assertTrue(pending.learning_interrupted_at)
        self.assertFalse(passed.learning_interrupted_at)
        self.assertFalse(separate.learning_interrupted_at)
        self.assertEqual(separate.state, "in_progress")
        self.assertEqual(member.completion, 100)
        self.assertEqual(member.completion_date, acquired_at)
        self.assertEqual(other_member.completion, 0)
        self.assertEqual(member._learning_progress()["percentage"], 100)

    def test_expired_before_institution_decision_stays_a_normal_server_expiry(self):
        course, slide = self.offer(obligations=["complete"])
        member = self.member(course)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slide.id)
        with patch.object(fields.Datetime, "now", return_value=attempt.deadline + timedelta(seconds=1)):
            slide.with_user(self.manager).action_learning_change_availability("Fictional closure after native expiry")
        self.assertEqual(attempt.end_datetime, attempt.deadline)
        self.assertFalse(attempt.learning_interrupted_at)
        self.assertEqual(member.completion, 100)


@tagged("post_install", "-at_install")
class TestInterruptedPortal(AutonomousCase, HttpCase):
    def test_direct_attempt_is_closed_then_reopened_history_has_no_correction_or_failure(self):
        course, slide = self.offer(obligations=["complete"])
        member = self.member(course)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slide.id)
        self.authenticate(self.learner.login, self.learner.login)
        path = "/my/learning-exams/%s" % attempt.id
        self.assertEqual(self.url_open(path).status_code, 200)
        slide.with_user(self.manager).action_learning_change_availability("Fictional private institution decision")
        self.assertEqual(self.url_open(path).status_code, 404)
        self.assertEqual(self.url_open("/my/learning/%s/exams/%s" % (member.id, slide.id)).status_code, 404)
        self.assertEqual(self.url_open("/my/learning/%s" % member.id).status_code, 200)
        slide.with_user(self.manager).action_learning_change_availability("Fictional explicit reopening", reopen=True)
        page = self.url_open(path)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Tentative interrompue", page.text)
        self.assertNotIn("PRIVATE FINAL CORRECTION", page.text)
        self.assertNotIn("Fictional private institution decision", page.text)
        self.assertEqual(page.headers["Cache-Control"], "no-store")
