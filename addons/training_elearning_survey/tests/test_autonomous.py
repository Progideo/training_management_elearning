"""Real native memberships and Survey answers on a composition without TM."""

from datetime import timedelta
from unittest.mock import patch
import re
import json
from odoo import fields, Command
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.tests import TransactionCase, HttpCase, new_test_user, tagged


class AutonomousCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.manager = new_test_user(
            cls.env, login="autonomous_coordinator", groups="training_elearning_survey.group_learning_exam_reader"
        )
        cls.author = new_test_user(
            cls.env,
            login="autonomous_author",
            groups="training_elearning.group_elearning_author,training_mock_exam.group_mock_exam_author",
        )
        cls.learner = new_test_user(cls.env, login="autonomous_learner", groups="base.group_portal")
        cls.other = new_test_user(cls.env, login="autonomous_other", groups="base.group_portal")
        cls.catalog = cls.env["training.course"].create({"name": "Fictional autonomous catalogue"})

    def exam(self):
        exam = (
            self.env["survey.survey"]
            .with_user(self.manager)
            .create(
                {
                    "title": "Fictional shared autonomous exam",
                    "training_course_id": self.catalog.id,
                    "time_limit": 10,
                    "scoring_success_min": 75,
                }
            )
        )
        self.env["survey.question"].with_user(self.manager).create(
            {
                "survey_id": exam.id,
                "title": "Fictional fixed choice",
                "question_type": "simple_choice",
                "answer_score": 2,
                "training_explanation": "PRIVATE FINAL CORRECTION",
                "suggested_answer_ids": [
                    Command.create({"value": "Expected", "is_correct": True}),
                    Command.create({"value": "Other"}),
                ],
            }
        )
        exam.action_mock_publish()
        return exam

    def offer(self, exams=None, obligations=None):
        exams = exams or [self.exam()]
        obligations = obligations or ["pass"] * len(exams)
        course = (
            self.env["slide.channel"]
            .with_user(self.manager)
            .create({"name": "Fictional autonomous edition", "training_course_id": self.catalog.id})
        )
        slides = self.env["slide.slide"]
        for exam, obligation in zip(exams, obligations):
            slides |= (
                self.env["slide.slide"]
                .with_user(self.manager)
                .create(
                    {
                        "channel_id": course.id,
                        "survey_id": exam.id,
                        "learning_exam_obligation": obligation,
                        "is_published": True,
                    }
                )
            )
        course.action_learning_publish()
        return course, slides

    def member(self, course, learner=None):
        learner = learner or self.learner
        row = (
            self.env["slide.channel.partner"]
            .with_user(self.manager)
            .create({"channel_id": course.id, "partner_id": learner.partner_id.id})
        )
        row.action_learning_activate(
            fields.Datetime.now() + timedelta(days=2), learner.id, "Fictional controlled access"
        )
        return row


@tagged("post_install", "-at_install")
class TestAutonomousExams(AutonomousCase):
    def test_native_shared_offers_obligations_and_unlimited_attempts(self):
        exam = self.exam()
        a, slides_a = self.offer([exam, self.exam()], ["complete", "optional"])
        b, slides_b = self.offer([exam], ["pass"])
        first, second = self.member(a), self.member(b)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        before_mail = self.env["mail.mail"].search_count([])
        one = service._start(first.id, slides_a[0].id)
        two = service._start(second.id, slides_b.id)
        self.assertEqual(one.survey_id, two.survey_id)
        self.assertNotEqual(one.mock_context_key, two.mock_context_key)
        self.assertEqual(service._start(first.id, slides_a[0].id), one)
        self.assertEqual(first.completion, 0)
        service._submit(one.id)
        self.assertEqual(first.completion, 100)
        self.assertEqual(second.completion, 0)
        q = two.predefined_question_ids[0]
        service._save(two.id, q.id, q.suggested_answer_ids.filtered("is_correct").ids, True)
        with self.assertRaises(AccessError):
            service._result(two)
        service._submit(two.id)
        self.assertEqual(second.completion, 100)
        retry = service._start(second.id, slides_b.id)
        self.assertFalse(retry.user_input_line_ids)
        self.assertFalse(retry.training_review_ids)
        service._submit(retry.id)
        self.assertEqual(second.completion, 100)
        self.assertTrue(second.active)
        self.assertEqual(second.learning_state, "active")
        self.assertEqual(self.env["mail.mail"].search_count([]), before_mail)
        self.assertFalse(two.slide_partner_id)
        self.assertFalse(exam.certification)

    def test_frozen_membership_renewal_and_model_guards(self):
        course, slides = self.offer()
        member = self.member(course)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slides.id)
        deadline = attempt.deadline
        rows = self.env["training.elearning.exam.requirement"].sudo().search([("membership_id", "=", member.id)])
        member.action_learning_activate(fields.Datetime.now() + timedelta(days=3), self.learner.id, "Fictional renewal")
        self.assertEqual(service._start(member.id, slides.id), attempt)
        self.assertEqual(attempt.deadline, deadline)
        self.assertEqual(
            rows, self.env["training.elearning.exam.requirement"].sudo().search([("membership_id", "=", member.id)])
        )
        with self.assertRaises(ValidationError):
            slides.with_user(self.manager).write({"learning_exam_obligation": "optional"})
        with self.assertRaises(ValidationError):
            self.env["slide.slide"].with_user(self.manager).create(
                {"channel_id": course.id, "survey_id": self.exam().id}
            )
        with self.assertRaises(AccessError):
            rows.write({"obligation": "optional"})
        with self.assertRaises(AccessError):
            member.with_user(self.learner).write({"learning_state": "active"})
        with self.assertRaises((AccessError, UserError)):
            slides.with_user(self.learner).action_mark_completed()
        with self.assertRaises(AccessError):
            slides._generate_certification_url()
        with self.assertRaises(AccessError):
            self.env["slide.slide.partner"].create(
                {"slide_id": slides.id, "partner_id": self.learner.partner_id.id, "completed": True}
            )
        with self.assertRaises(AccessError):
            service.with_user(self.other)._submit(attempt.id)
        self.assertFalse(attempt.with_user(self.author).search([("id", "=", attempt.id)]))
        self.assertTrue(attempt.with_user(self.manager).search([("id", "=", attempt.id)]))

    def test_strict_server_deadline_expiry_suspension_and_renewal(self):
        course, slides = self.offer(obligations=["complete"])
        member = self.member(course)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slides.id)
        with patch.object(fields.Datetime, "now", return_value=attempt.deadline):
            self.assertEqual(
                service._save(attempt.id, attempt.predefined_question_ids[0].id, [], False), {"done": True}
            )
        self.assertEqual(attempt.end_datetime, attempt.deadline)
        self.assertFalse(attempt.user_input_line_ids)
        self.assertEqual(member.completion, 100)
        member.action_learning_suspend("Fictional suspension")
        with self.assertRaises(AccessError):
            service._result(attempt)
        member.action_learning_activate(
            fields.Datetime.now() + timedelta(days=3), self.learner.id, "Fictional reactivation"
        )
        self.assertEqual(service._result(attempt)["percentage"], 0)
        member._learning_store({"learning_ends_at": fields.Datetime.now() - timedelta(seconds=1)})
        with self.assertRaises(AccessError):
            service._result(attempt)
        with self.assertRaises(AccessError):
            service._start(member.id, slides.id)
        self.assertEqual(member._learning_progress()["percentage"], 100)

    def test_mixed_native_lessons_exam_prerequisites_and_optional_obligations(self):
        exam = self.exam()
        course = (
            self.env["slide.channel"]
            .with_user(self.manager)
            .create({"name": "Fictional mixed edition", "training_course_id": self.catalog.id})
        )
        article = (
            self.env["slide.slide"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional mixed article",
                    "channel_id": course.id,
                    "slide_category": "article",
                    "html_content": "<p>Fictional lesson</p>",
                    "is_published": True,
                }
            )
        )
        required = (
            self.env["slide.slide"]
            .with_user(self.manager)
            .create(
                {
                    "channel_id": course.id,
                    "survey_id": exam.id,
                    "learning_exam_obligation": "pass",
                    "learning_prerequisite_ids": [Command.set(article.ids)],
                    "is_published": True,
                }
            )
        )
        optional = (
            self.env["slide.slide"]
            .with_user(self.manager)
            .create(
                {
                    "channel_id": course.id,
                    "survey_id": self.exam().id,
                    "learning_exam_obligation": "optional",
                    "is_published": True,
                }
            )
        )
        course.action_learning_publish()
        financial = new_test_user(
            self.env, login="fictional_mixed_financial", groups="training_elearning.group_elearning_manager"
        )
        member = (
            self.env["slide.channel.partner"]
            .with_user(financial)
            .create({"channel_id": course.id, "partner_id": self.learner.partner_id.id})
        )
        member.action_learning_activate(
            fields.Datetime.now() + timedelta(days=2), self.learner.id, "Fictional mixed activation"
        )
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        with self.assertRaises(AccessError):
            service._start(member.id, required.id)
        # Display order is never a prerequisite; this optional exam is open.
        attempt = service._start(member.id, optional.id)
        service._submit(attempt.id)
        self.assertEqual(member.completion, 0)
        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, article.id)
        self.assertEqual(member.completion, 50)
        attempt = service._start(member.id, required.id)
        question = attempt.predefined_question_ids[0]
        service._save(attempt.id, question.id, question.suggested_answer_ids.filtered("is_correct").ids, False)
        service._submit(attempt.id)
        self.assertEqual(member.completion, 100)
        leaf = (
            self.env["slide.slide.partner"]
            .sudo()
            .search([("slide_id", "=", required.id), ("partner_id", "=", self.learner.partner_id.id)])
        )
        self.assertTrue(leaf.completed)
        with self.assertRaises(AccessError):
            self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, required.id)
        self.assertEqual(
            self.env["training.elearning.exam.requirement"].sudo().search_count([("membership_id", "=", member.id)]), 2
        )

    def test_legacy_typed_requirement_survives_source_archival_without_plan_backfill(self):
        course, slide = self.offer(obligations=["complete"])
        member = self.member(course)
        member._learning_store({"learning_plan": False})
        slide.with_user(self.manager).write({"active": False})
        self.assertEqual(member._learning_progress()["required"], 1)
        self.assertEqual(member.completion, 0)
        self.assertFalse(member.learning_plan)
        with self.assertRaises(AccessError):
            self.env["training.elearning.exam.service"].with_user(self.learner)._start(member.id, slide.id)

    def test_standard_unmanaged_course_still_uses_native_completion(self):
        course = (
            self.env["slide.channel"]
            .with_user(self.manager)
            .create({"name": "Fictional standard course", "is_published": True})
        )
        slide = (
            self.env["slide.slide"]
            .with_user(self.manager)
            .create(
                {
                    "channel_id": course.id,
                    "name": "Standard article",
                    "slide_category": "article",
                    "html_content": "<p>Fictional native article</p>",
                    "is_published": True,
                }
            )
        )
        slide.action_mark_completed()
        member = (
            self.env["slide.channel.partner"]
            .sudo()
            .search([("channel_id", "=", course.id), ("partner_id", "=", self.manager.partner_id.id)])
        )
        self.assertEqual(member.completion, 100)

    def test_company_boundary_and_native_membership_move_cannot_bypass_activation(self):
        course, slides = self.offer()
        member = self.member(course)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slides.id)
        self.assertEqual(attempt.mock_company_id, self.company)
        foreign = self.env["res.company"].create({"name": "Fictional foreign operator"})
        foreign_manager = new_test_user(
            self.env,
            login="autonomous_foreign_coordinator",
            groups="training_elearning_survey.group_learning_exam_reader",
            company_id=foreign.id,
            company_ids=[Command.set(foreign.ids)],
        )
        self.assertFalse(course.with_user(foreign_manager).search([("id", "=", course.id)]))
        self.assertFalse(attempt.with_user(foreign_manager).search([("id", "=", attempt.id)]))
        with self.assertRaises(AccessError):
            member.with_user(foreign_manager).action_learning_activate(
                fields.Datetime.now() + timedelta(days=3), self.learner.id, "Fictional rejected renewal"
            )
        standard = self.env["slide.channel"].with_user(self.manager).create({"name": "Fictional ordinary course"})
        ordinary_member = (
            self.env["slide.channel.partner"]
            .sudo()
            .search([("channel_id", "=", standard.id), ("partner_id", "=", self.manager.partner_id.id)])
        )
        with self.assertRaises(AccessError):
            ordinary_member.with_user(self.manager).write({"channel_id": course.id})
        file = self.env["ir.attachment"].create(
            {
                "name": "Fictional private edition file",
                "raw": b"private learning metadata",
                "res_model": "slide.channel",
                "res_id": course.id,
                "public": True,
            }
        )
        for user in (self.learner, self.other, foreign_manager):
            self.assertFalse(file.with_user(user).search([("id", "=", file.id)]))
            with self.assertRaises(AccessError):
                file.with_user(user).sudo()._to_http_stream()


@tagged("post_install", "-at_install")
class TestAutonomousPortal(AutonomousCase, HttpCase):
    def test_private_native_bypass_csrf_and_correction(self):
        course, slides = self.offer()
        member = self.member(course)
        self.authenticate(self.learner.login, self.learner.login)
        page = self.url_open("/my/learning/%s" % member.id)
        self.assertEqual(page.status_code, 200)
        for path in (
            "/slides/%s" % course.id,
            "/slides/slide/%s" % slides.id,
            "/slides_survey/slide/get_certification_url?slide_id=%s" % slides.id,
        ):
            self.assertIn(self.url_open(path).status_code, (403, 404))
        rpc = self.url_open(
            "/slides/channel/join",
            data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {"channel_id": course.id}, "id": 1}),
            headers={"Content-Type": "application/json"},
        )
        self.assertIn(rpc.status_code, (403, 404))
        start = "/my/learning/%s/exams/%s" % (member.id, slides.id)
        page = self.url_open(start)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        opened = self.url_open(start, data={"csrf_token": csrf})
        self.assertEqual(opened.status_code, 200)
        self.assertNotIn("PRIVATE FINAL CORRECTION", opened.text)
        attempt = self.env["survey.user_input"].sudo().search([("learning_membership_id", "=", member.id)])
        self.assertIn("/my/learning-exams/%s/save" % attempt.id, opened.text)
        save = "/my/learning-exams/%s/save" % attempt.id
        self.assertEqual(self.url_open(save, data={"kind": "submit"}).status_code, 400)
        done = self.url_open(save, data={"csrf_token": csrf, "kind": "submit"})
        self.assertEqual(done.status_code, 200)
        result = self.url_open("/my/learning-exams/%s" % attempt.id)
        self.assertIn("PRIVATE FINAL CORRECTION", result.text)
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        self.authenticate(self.other.login, self.other.login)
        self.assertEqual(self.url_open("/my/learning/%s" % member.id).status_code, 404)
        self.assertEqual(self.url_open("/my/learning-exams/%s" % attempt.id).status_code, 404)
