"""The same package bytes support separate TM and autonomous native progressions."""

from datetime import timedelta
from uuid import uuid4
from odoo import fields
from odoo.tests import new_test_user, tagged
from .test_attempt import RuntimeCase


@tagged("post_install", "-at_install")
class TestContextIsolation(RuntimeCase):
    def test_shared_version_has_separate_attempts_leases_and_acquisitions(self):
        if "training.elearning.interactive.attempt" not in self.env:
            self.skipTest("The autonomous reader adapter is qualified in the coexistence composition")
        enrollment, usage = self.setup_runtime()
        version = usage.version_id
        file_ids = self.env["training.elearning.file"].sudo().search([("version_id", "=", version.id)]).ids
        editor = new_test_user(
            self.env, login="fictional_coexist_interactive_editor", groups="training_elearning.group_elearning_manager"
        )
        courses = self.env["slide.channel"]
        slides = self.env["slide.slide"]
        members = self.env["slide.channel.partner"]
        for index in range(2):
            course = (
                self.env["slide.channel"]
                .with_user(editor)
                .create(
                    {"name": "Fictional coexist edition %s" % index, "training_course_id": self.program.course_id.id}
                )
            )
            slide = (
                self.env["slide.slide"]
                .with_user(editor)
                .create(
                    {
                        "channel_id": course.id,
                        "learning_interactive_version_id": version.id,
                        "learning_interactive_rule": "score",
                        "is_published": True,
                    }
                )
            )
            course.action_learning_publish()
            member = (
                self.env["slide.channel.partner"]
                .with_user(editor)
                .create({"channel_id": course.id, "partner_id": self.portal.partner_id.id})
            )
            member.action_learning_activate(
                fields.Datetime.now() + timedelta(days=2), self.portal.id, "Fictional coexist standalone grant"
            )
            courses |= course
            slides |= slide
            members |= member
        own = (
            self.env["training.elearning.interactive.attempt"]
            .with_user(self.portal)
            ._start(members[0].id, slides[0].id, str(uuid4()))
        )
        framed = self.start(enrollment, usage)
        own._save(
            "own-result",
            1,
            {"state": {"mode": "AUTONOMOUS"}, "result": {"score": 100, "maximum": 100, "completed": True}},
        )
        self.assertEqual(members[0].completion, 100)
        self.assertFalse(self.service()._complete(enrollment, usage.activity_id))
        framed._save(
            "tm-result", 1, {"state": {"mode": "TM"}, "result": {"score": 100, "maximum": 100, "completed": True}}
        )
        self.assertTrue(self.service()._complete(enrollment, usage.activity_id))
        self.assertEqual(members[1].completion, 0)
        params = self.env["ir.config_parameter"]
        params.set_str("training_elearning.portal_origin", "https://portal.example.invalid")
        params.set_str("training_elearning.content_origin", "https://content.example.invalid")
        leases = self.env["training.elearning.lease"].with_user(self.portal)
        standalone, _own_token = leases.with_context(default_attempt_id=framed.id)._issue(version, own)
        supervised, _tm_token = leases.with_context(default_learning_attempt_id=own.id)._issue(version, framed)
        self.assertFalse(standalone.attempt_id)
        self.assertFalse(supervised.learning_attempt_id)
        self.assertFalse(standalone._is_preview())
        self.assertFalse(supervised._is_preview())
        self.assertEqual(standalone._content_snapshot()["state"], {"mode": "AUTONOMOUS"})
        self.assertEqual(supervised._content_snapshot()["state"], {"mode": "TM"})
        self.assertIn("/my/learning-interactive/", standalone._player_context()["save"])
        self.assertIn("/training/interactive/", supervised._player_context()["save"])
        self.assertEqual(
            self.env["training.elearning.file"].sudo().search([("version_id", "=", version.id)]).ids, file_ids
        )
