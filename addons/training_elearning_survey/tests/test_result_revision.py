"""Motivated shared results, immutable answers and context-specific staff rights."""

from uuid import uuid4
from unittest.mock import patch
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, new_test_user, tagged
from .test_autonomous import AutonomousCase


@tagged("post_install", "-at_install")
class TestAutonomousResultRevision(AutonomousCase):
    def failed(self):
        course, slide = self.offer()
        member = self.member(course)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slide.id)
        question = attempt.predefined_question_ids[0]
        service._save(
            attempt.id,
            question.id,
            question.suggested_answer_ids.filtered(lambda choice: not choice.is_correct).ids,
            True,
        )
        service._submit(attempt.id)
        return member, attempt, question, service

    def wizard(self, attempt, user=None):
        return Form(
            self.env["training.exam.revise"]
            .with_user(user or self.manager)
            .with_context(active_model="survey.user_input", active_id=attempt.id),
            view="training_mock_exam.revise_form",
        )

    def test_revised_scores_keep_native_answers_first_acquisition_and_idempotence(self):
        member, attempt, question, service = self.failed()
        original = attempt.read(
            [
                "start_datetime",
                "deadline",
                "end_datetime",
                "state",
                "scoring_total",
                "scoring_percentage",
                "training_review_ids",
            ]
        )[0]
        answers = attempt.user_input_line_ids.read(
            ["id", "question_id", "suggested_answer_id", "answer_score", "answer_is_correct"]
        )
        revisions = self.env["training.exam.revision"].with_user(self.manager)
        key = str(uuid4())
        first = revisions._record(
            attempt, {str(question.id): 2}, "Fictional first motivated correction", request_key=key, expected_previous=0
        )
        notice = self.env["training.elearning.reminder"].sudo().search([("result_revision_id", "=", first.id)])
        self.assertEqual(notice.state, "queued")
        self.assertEqual(notice.partner_id, self.learner.partner_id)
        self.assertNotIn(first.reason, str(notice.mail_id.body_html))
        self.assertNotIn("PRIVATE FINAL CORRECTION", str(notice.mail_id.body_html))
        self.assertEqual(service._result(attempt)["percentage"], 100)
        self.assertEqual(member.completion, 100)
        leaf = (
            self.env["slide.slide.partner"]
            .sudo()
            .search([("slide_id", "=", attempt.learning_slide_id.id), ("partner_id", "=", self.learner.partner_id.id)])
        )
        stamp = leaf.learning_completed_at
        second = revisions._record(
            attempt,
            {str(question.id): 0},
            "Fictional later correction without acquisition invalidation",
            request_key=str(uuid4()),
            expected_previous=first.id,
        )
        self.assertEqual(second.previous_id, first)
        self.assertEqual(service._result(attempt)["percentage"], 0)
        self.assertEqual(member.completion, 100)
        self.assertEqual(leaf.learning_completed_at, stamp)
        self.assertEqual(revisions._record(attempt, {str(question.id): 2}, first.reason, request_key=key), first)
        self.assertEqual(attempt.read(list(original.keys() - {"id"}))[0], original)
        self.assertEqual(attempt.user_input_line_ids.read(list(answers[0].keys())), answers)
        with self.assertRaises(ValidationError):
            revisions._record(attempt, {str(question.id): 1}, "Divergent replay", request_key=key)
        with self.assertRaises(AccessError):
            first.with_user(self.learner).read(["points_by_question"])
        with self.assertRaises(AccessError):
            self.env["ir.attachment"].with_user(self.manager).create(
                {"name": "forbidden-result.txt", "raw": b"PRIVATE RESULT", "res_model": first._name, "res_id": first.id}
            )
        with self.assertRaises(AccessError):
            self.env["ir.binary"].with_user(self.learner)._get_stream_from(first.sudo(), "reason")

        for user in (self.learner, self.author, self.other):
            with self.assertRaises(AccessError):
                revisions.with_user(user)._record(attempt, {str(question.id): 2}, "Forbidden role")
        for value in (True, "2", float("nan"), float("inf"), -1, 3, 10**400):
            with self.subTest(value=type(value).__name__), self.assertRaises(ValidationError):
                revisions._record(attempt, {str(question.id): value}, "Fictional invalid points")

    def test_native_form_replay_stale_form_and_atomic_projection(self):
        member, attempt, question, _service = self.failed()
        with self.wizard(attempt) as prepared:
            prepared.reason = "Fictional native motivated correction"
            with prepared.line_ids.edit(0) as line:
                line.points = 2
        with self.wizard(attempt) as outdated:
            outdated.reason = "Fictional stale correction"
        wizard = prepared.record
        wizard.action_apply()
        count = self.env["training.exam.revision"].sudo().search_count([("attempt_id", "=", attempt.id)])
        wizard.action_apply()
        self.assertEqual(
            self.env["training.exam.revision"].sudo().search_count([("attempt_id", "=", attempt.id)]), count
        )
        with self.assertRaises(ValidationError):
            outdated.record.action_apply()
        self.assertEqual(member.completion, 100)
        # A failure after the real projection must roll back the event and native
        # acquisition inside the factory, without a test-created savepoint.
        another_member, another, other_question, _ = self.failed()
        original = type(another)._mock_revision_project

        def fail_after_projection(record):
            original(record)
            raise ValidationError(self.env._("Injected revision projection failure"))

        with patch.object(type(another), "_mock_revision_project", fail_after_projection):
            try:
                self.env["training.exam.revision"].with_user(self.manager)._record(
                    another, {str(other_question.id): 2}, "Fictional rollback case", request_key=str(uuid4())
                )
            except ValidationError:  # pylint: disable=except-pass
                pass
            else:
                self.fail("Projection error was swallowed")
        self.assertFalse(self.env["training.exam.revision"].sudo().search_count([("attempt_id", "=", another.id)]))
        self.assertEqual(another_member.completion, 0)
        self.assertEqual(another.mock_revision_serial, 0)

    def test_company_and_revoked_application_role_protect_raw_history_and_forms(self):
        _member, attempt, question, _service = self.failed()
        other_company = self.env["res.company"].create({"name": "Fictional revision company B"})
        foreign = new_test_user(
            self.env,
            login="fictional_revision_foreign",
            groups="training_elearning_survey.group_learning_exam_reader",
            company_id=other_company.id,
            company_ids=[Command.set(other_company.ids)],
        )
        revision = (
            self.env["training.exam.revision"]
            .with_user(self.manager)
            ._record(attempt, {str(question.id): 2}, "Fictional bounded revision")
        )
        with self.assertRaises(AccessError):
            revision.with_user(foreign).read(["reason"])
        with self.assertRaises(AccessError):
            self.env["training.exam.revision"].with_user(foreign)._record(
                attempt, {str(question.id): 0}, "Forbidden company"
            )
        if "training.enrollment" not in self.env:
            return  # The role-union case is executed in the ten-addon composition.
        dual = new_test_user(
            self.env,
            login="fictional_revision_dual",
            groups="training_elearning_survey.group_learning_exam_reader,training_management.group_training_coordinator",
        )
        with self.wizard(attempt, dual) as form:
            form.reason = "Fictional pending role change"
        wizard = form.record
        lines = wizard.line_ids
        dual.group_ids = [Command.unlink(self.env.ref("training_elearning_survey.group_learning_exam_reader").id)]
        self.assertTrue(dual.has_group("training_management.group_training_coordinator"))
        for record, names in ((revision, ["points_by_question"]), (wizard, ["reason"]), (lines, ["points"])):
            with self.assertRaises(AccessError):
                record.with_user(dual).read(names)
        with self.assertRaises(AccessError):
            wizard.with_user(dual).action_apply()

    def test_purchase_cutoff_excludes_later_attempt_but_retains_late_original_correction(self):
        if "training.elearning.sale.course.report" not in self.env:
            self.skipTest("Purchase result boundaries are qualified with the Sales integration")
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta
        from odoo import fields
        from odoo.addons.training_elearning_sale.tests.test_purchase_report import TestPurchaseReports

        self.commercial = new_test_user(
            self.env,
            login="fictional_result_purchase_manager",
            groups="training_elearning_sale.group_learning_sales_manager",
        )
        self.buyer = self.env["res.partner"].create({"name": "Fictional result purchaser"})
        member, original, question, service = self.failed()
        old = TestPurchaseReports.buy(self, member.channel_id)
        end = old.access_ends_at
        with patch.object(fields.Datetime, "now", return_value=end - timedelta(days=3)):
            current = TestPurchaseReports.buy(self, member.channel_id, 6)
        with patch.object(fields.Datetime, "now", return_value=end + timedelta(days=1)):
            self.assertEqual(old._purchase_summary()["percentage"], 0)
        late = end + timedelta(days=2)
        revisions = self.env["training.exam.revision"].with_user(self.manager)
        with patch.object(fields.Datetime, "now", return_value=late):
            newer = service._start(member.id, original.learning_slide_id.id)
            service._submit(newer.id)
            revisions._record(newer, {str(question.id): 2}, "Fictional correction of a later funded attempt")
            self.assertEqual(current._purchase_summary()["percentage"], 100)
            self.assertEqual(old._purchase_summary()["percentage"], 0)
            self.assertEqual(old._purchase_summary()["closed_at"], end)
        final = end + timedelta(days=4)
        with patch.object(fields.Datetime, "now", return_value=final):
            revisions._record(original, {str(question.id): 2}, "Fictional late correction of the original submission")
            summary = old._purchase_summary()
            self.assertTrue(summary["complete"])
            self.assertEqual(summary["closed_at"], final)
            self.assertTrue(old.report_course_ids.sudo().snapshot_history)
            representative = new_test_user(
                self.env, login="fictional_result_purchase_representative", groups="base.group_portal"
            )
            mandate = (
                self.env["training.elearning.sale.mandate"]
                .with_user(self.commercial)
                .create(
                    {
                        "line_id": old.line_id.id,
                        "user_id": representative.id,
                        "valid_until": end + timedelta(days=500),
                        "reason": "Fictional original purchase mandate",
                    }
                )
            )
            mandate.action_grant()
            company_service = self.env["training.elearning.company.service"].with_user(representative)
            self.assertEqual(company_service._ends_at(mandate), final + relativedelta(months=3))
