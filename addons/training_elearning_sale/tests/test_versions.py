"""Sold plans, shared exam revisions and native membership history."""

from datetime import timedelta
from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged
from .test_sale import SalesCase


@tagged("post_install", "-at_install")
class TestSoldVersions(SalesCase):
    def test_new_exam_version_keeps_sold_and_activated_obligations(self):
        course, slide, product = self.offer()
        order, line = self.order(product, 2)
        order.action_confirm()
        line.action_learning_authorize("Fictional confirmed agreement")
        first = self.seat(line)
        first.action_learning_activate()
        member = first.membership_id
        old = slide.survey_id.with_user(self.author)
        service = self.env["training.elearning.exam.service"].with_user(self.learner)
        attempt = service._start(member.id, slide.id)
        deadline = attempt.deadline
        action = old.action_mock_new_version()
        new = self.env["survey.survey"].with_user(self.author).browse(action["res_id"])
        new.write(
            {"training_version": "2", "training_revision_reason": "Fictional changed scoring version", "time_limit": 15}
        )
        new.action_mock_publish()
        revision = (
            self.env["training.elearning.exam.revision"]
            .with_user(self.author)
            .create({"slide_id": slide.id, "exam_id": new.id, "reason": "Fictional selection for future buyers"})
        )
        with self.assertRaises(ValidationError):
            slide.with_user(self.author).write({"survey_id": new.id})
        revision.action_apply()
        self.assertEqual(slide.survey_id, new)
        self.assertEqual(line.learning_plan["slides"][0]["exam"], old.id)
        self.assertEqual(service._start(member.id, slide.id), attempt)
        self.assertEqual(attempt.deadline, deadline)
        pending = self.seat(line, self.other)
        pending.action_learning_activate()
        other_service = service.with_user(self.other)
        self.assertEqual(other_service._start(pending.membership_id.id, slide.id).survey_id, old)
        next_order, next_line = self.order(product)
        next_order.action_confirm()
        next_line.action_learning_authorize("Fictional later agreement")
        fresh = new_test_user(self.env, login="fictional_new_version_learner", groups="base.group_portal")
        next_seat = self.seat(next_line, fresh)
        next_seat.action_learning_activate()
        self.assertEqual(service.with_user(fresh)._start(next_seat.membership_id.id, slide.id).survey_id, new)
        member.with_user(self.manager).action_learning_activate(
            fields.Datetime.now() + timedelta(days=250), self.learner.id, "Fictional later renewal"
        )
        self.assertEqual(service._start(member.id, slide.id), attempt)
        self.assertEqual(slide.learning_exam_revision_log[0]["actor"], self.author.id)
        with self.assertRaises(AccessError):
            slide.with_user(self.author).write({"learning_exam_revision_log": False})
        with self.assertRaises(AccessError):
            line.write({"learning_plan": False})

    def test_exam_revision_keeps_family_company_roles_and_audit_boundaries(self):
        course, slide, product = self.offer()
        other_course, other_slide, _product = self.offer()
        order, line = self.order(product)
        order.action_confirm()
        wizard_model = self.env["training.elearning.exam.revision"]
        for exam in (slide.survey_id, other_slide.survey_id):
            with self.assertRaises(ValidationError):
                wizard_model.with_user(self.author).create(
                    {"slide_id": slide.id, "exam_id": exam.id, "reason": "Fictional inadmissible version"}
                ).action_apply()
        old = slide.survey_id.with_user(self.author)
        new = self.env["survey.survey"].with_user(self.author).browse(old.action_mock_new_version()["res_id"])
        new.write(
            {
                "training_version": "Second reference",
                "training_revision_reason": "Fictional alternative published reference",
            }
        )
        new.action_mock_publish()
        with self.assertRaises(AccessError):
            wizard_model.with_user(self.manager).create(
                {
                    "slide_id": slide.id,
                    "exam_id": new.id,
                    "reason": "Fictional financial role without question authoring",
                }
            ).action_apply()
        with self.assertRaises(AccessError):
            wizard_model.with_user(self.learner).create(
                {"slide_id": slide.id, "exam_id": new.id, "reason": "Fictional learner forgery"}
            )
        self.assertFalse(slide.learning_exam_revision_log)
        self.assertEqual(line.learning_plan["slides"][0]["exam"], old.id)
        self.assertFalse(other_course.learning_bound_at)

    def test_legacy_sold_plan_is_captured_only_at_explicit_revision(self):
        course, slide, product = self.offer()
        order, line = self.order(product)
        order.action_confirm()
        line._learning_store({"learning_plan": False})
        old = slide.survey_id.with_user(self.author)
        new = self.env["survey.survey"].with_user(self.author).browse(old.action_mock_new_version()["res_id"])
        new.write({"training_version": "2", "training_revision_reason": "Fictional revised version"})
        new.action_mock_publish()
        self.assertFalse(line.learning_plan)
        self.env["training.elearning.exam.revision"].with_user(self.author).create(
            {"slide_id": slide.id, "exam_id": new.id, "reason": "Fictional explicit legacy selection"}
        ).action_apply()
        self.assertEqual(line.learning_plan["slides"][0]["exam"], old.id)
        self.assertEqual(slide.survey_id, new)
        self.assertTrue(course.learning_bound_at)
