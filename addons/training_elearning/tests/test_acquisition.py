"""Explicit acquisition decisions preserve native proofs, rights and issued bytes."""

from uuid import uuid4
from unittest.mock import patch
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, new_test_user, tagged
from .test_certificate import CertificateCase
from .test_interactive import InteractiveCase


@tagged("post_install", "-at_install")
class TestAcquisitionInvalidation(CertificateCase):
    def decision(self, member, slide, key=None, withdraw=False):
        return (
            self.env["training.elearning.acquisition.invalidation"]
            .with_user(self.pedagogy)
            ._invalidate(
                member,
                slide.id,
                "Fictional motivated acquisition decision",
                key or str(uuid4()),
                withdraw_certificates=withdraw,
            )
        )

    def test_native_form_replay_new_proof_keeps_first_date_and_rights(self):
        course, slide, member = self.completed_course()
        leaf = self.env["slide.slide.partner"].search(
            [("slide_id", "=", slide.id), ("partner_id", "=", self.learner.partner_id.id)]
        )
        original = leaf.learning_completed_at
        rights = member.read(["learning_started_at", "learning_ends_at", "learning_access_log"])
        action = member.with_user(self.pedagogy).action_learning_invalidate_acquisition()
        with Form(
            self.env[action["res_model"]].with_user(self.pedagogy).with_context(**action["context"]),
            view="training_elearning.acquisition_invalidate_form",
        ) as form:
            form.slide_id = slide
            form.reason = "Fictional native dialogue decision"
        wizard = form.record
        event = self.env["training.elearning.acquisition.invalidation"].browse(wizard.action_apply()["res_id"])
        self.assertEqual(wizard.action_apply()["res_id"], event.id)
        self.assertEqual(member.completion, 0)
        self.assertEqual(leaf.learning_completed_at, original)
        self.assertEqual(rights, member.read(["learning_started_at", "learning_ends_at", "learning_access_log"]))
        self.assertFalse(leaf.completed)
        member._learning_sync_progress()
        self.assertEqual(member.completion, 0)
        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, slide.id)
        self.assertEqual(member.completion, 100)
        self.assertTrue(event.restored_at)
        self.assertEqual(leaf.learning_completed_at, original)
        self.assertTrue(leaf.learning_valid_completed_at)
        self.assertEqual(wizard.action_apply()["res_id"], event.id)
        self.assertEqual(member.completion, 100)

    def test_certificate_withdrawal_is_explicit_and_keeps_original_pdf(self):
        member, _consent, document = self.issued()
        slide = member.channel_id.slide_ids
        raw, token = document.pdf.content, document.token
        event = self.decision(member, slide)
        self.assertEqual(document.state, "valid")
        self.assertTrue(event.needs_certificate_review)
        self.assertEqual(event.certificate_ids, document)
        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, slide.id)
        second = self.decision(member, slide, withdraw=True)
        self.assertEqual(document.state, "withdrawn")
        self.assertFalse(second.needs_certificate_review)
        self.assertEqual(document.pdf.content, raw)
        self.assertEqual(document.token, token)

    def test_decision_checks_role_company_activity_and_immutable_history(self):
        _course, slide, member = self.completed_course()
        model = self.env["training.elearning.acquisition.invalidation"]
        for user in (self.learner, self.manager):
            with self.assertRaises(AccessError):
                model.with_user(user)._invalidate(member, slide.id, "Fictional denied", str(uuid4()))
        with self.assertRaises(ValidationError):
            model.with_user(self.pedagogy)._invalidate(member, slide.id, " ", str(uuid4()))
        other_course = self.course()
        other_slide = self.article(other_course)
        other_course.action_learning_publish()
        with self.assertRaises(AccessError):
            self.decision(member, other_slide)
        event = self.decision(member, slide)
        for user in (self.learner, self.manager):
            with self.assertRaises(AccessError):
                event.with_user(user).read(["reason"])
        with self.assertRaises(AccessError):
            event.write({"reason": "Forged"})
        with self.assertRaises(AccessError):
            event.unlink()
        with self.assertRaises(AccessError):
            model.create({})
        with self.assertRaises(ValidationError):
            self.decision(member, slide, key=event.request_key, withdraw=True)
        self.pedagogy.write(
            {"group_ids": [Command.unlink(self.env.ref("training_elearning.group_elearning_pedagogy_manager").id)]}
        )
        with self.assertRaises(AccessError):
            self.decision(member, slide, key=event.request_key)

    def test_path_certificate_only_changes_when_required_acquisition_is_affected(self):
        course, slide = self.edition("Fictional required acquisition")
        optional, optional_slide = self.edition("Fictional optional acquisition")
        activation = self.activation(self.path([(course, True), (optional, False)]))
        registration = activation.registration_id
        member, optional_member = registration._member(course.id), registration._member(optional.id)
        service = self.env["training.elearning.service"].with_user(self.learner)
        service._declare(member.id, slide.id)
        service._declare(optional_member.id, optional_slide.id)
        document = self.consent(registration=registration).with_user(self.pedagogy)._issue()
        raw = document.pdf.content
        event = self.decision(optional_member, optional_slide, withdraw=True)
        self.assertFalse(event.certificate_ids)
        self.assertEqual(document.state, "valid")
        event = self.decision(member, slide, withdraw=True)
        self.assertEqual(event.certificate_ids, document)
        self.assertEqual(document.state, "withdrawn")
        self.assertEqual(document.pdf.content, raw)

    def test_failed_decision_rolls_back_projection_and_foreign_access_is_denied(self):
        _course, slide, member = self.completed_course()
        model = self.env["training.elearning.acquisition.invalidation"].with_user(self.pedagogy)
        with patch.object(
            type(model), "_affected_certificates", side_effect=ValidationError("Fictional interrupted decision")
        ):
            try:
                self.decision(member, slide)
            except ValidationError:  # pylint: disable=except-pass
                pass  # The production savepoint, not a test savepoint, must undo the mutation.
            else:
                self.fail("The interrupted decision was accepted")
        self.assertEqual(member.completion, 100)
        self.assertFalse(model.search([("membership_id", "=", member.id)]))
        foreign = self.env["res.company"].create({"name": "Fictional foreign decision operator"})
        coordinator = new_test_user(
            self.env,
            login="fictional_foreign_acquisition_coordinator",
            groups="training_elearning.group_elearning_pedagogy_manager",
            company_id=foreign.id,
            company_ids=[Command.set(foreign.ids)],
        )
        with self.assertRaises(AccessError):
            model.with_user(coordinator)._invalidate(member, slide.id, "Fictional foreign decision", str(uuid4()))
        event = self.decision(member, slide)
        with self.assertRaises(AccessError):
            event.with_user(coordinator).read(["reason"])
        with self.assertRaises(AccessError):
            self.env["ir.attachment"].create(
                {
                    "name": "Fictional forbidden decision attachment",
                    "res_model": event._name,
                    "res_id": event.id,
                    "type": "url",
                    "url": "https://example.invalid/private",
                }
            )
        with self.assertRaises(AccessError):
            self.env["ir.binary"]._find_record(res_model=event._name, res_id=event.id, field="reason")

    def test_existing_identity_cannot_move_operating_company(self):
        course, _slide, _member = self.completed_course()
        foreign = self.env["res.company"].create({"name": "Fictional foreign acquisition operator"})
        with self.assertRaises(ValidationError):
            course.training_course_id.write({"company_id": foreign.id})


@tagged("post_install", "-at_install")
class TestInteractiveAcquisitionInvalidation(InteractiveCase):
    def test_old_attempt_cannot_restore_invalidated_acquisition(self):
        pedagogy = new_test_user(
            self.env,
            login="fictional_interactive_invalidation",
            groups="training_elearning.group_elearning_pedagogy_manager",
        )
        _course, slide, _version, member = self.interactive()
        attempt = self.start(member, slide)
        payload = {
            "state": {"page": "Fictional retained page"},
            "result": {"score": 100, "maximum": 100, "completed": True},
        }
        attempt._save("first", 1, payload)
        first_date = member.completion_date
        event = (
            self.env["training.elearning.acquisition.invalidation"]
            .with_user(pedagogy)
            ._invalidate(member, slide.id, "Fictional package decision", str(uuid4()))
        )
        self.assertEqual(member.completion, 0)
        with self.assertRaises(AccessError):
            attempt._save("old-proof", 2, payload)
        new = self.start(member, slide)
        self.assertNotEqual(new, attempt)
        self.assertEqual(new._snapshot()["state"], {})
        new._save("new-proof", 1, payload)
        self.assertEqual(member.completion, 100)
        self.assertTrue(event.restored_at)
        self.assertTrue(first_date)
