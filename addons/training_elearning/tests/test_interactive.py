"""Real shared packages and native autonomous evidence, with atomic and scoped saves."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, Form, new_test_user, tagged
from odoo.addons.training_interactive.tests.test_library import package, h5p_package
from .test_activities import LessonCase


class InteractiveCase(LessonCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.librarian = new_test_user(
            cls.env, login="fictional_interactive_librarian", groups="training_interactive.group_interactive_manager"
        )

    def version(self, kind="scorm12", resource=None, number="1"):
        resource = resource or self.env["training.elearning.resource"].with_user(self.manager).create(
            {"name": "Fictional common package", "format": kind}
        )
        version = (
            self.env["training.elearning.version"]
            .with_user(self.manager)
            ._import(
                resource,
                number,
                h5p_package() if kind == "h5p" else package(),
                "Fictional test licence",
                "Fictional test provenance",
            )
        )
        version.action_publish()
        return version

    def interactive(self, kind="scorm12", rule="score"):
        version = self.version(kind)
        course = self.course()
        slide = (
            self.env["slide.slide"]
            .with_user(self.manager)
            .create(
                {
                    "channel_id": course.id,
                    "learning_interactive_version_id": version.id,
                    "learning_interactive_rule": rule,
                    "is_published": True,
                }
            )
        )
        course.action_learning_publish()
        return course, slide, version, self.member(course)

    def start(self, member, slide, *, new=False, key=None):
        return (
            self.env["training.elearning.interactive.attempt"]
            .with_user(self.learner)
            ._start(member.id, slide.id, key or str(uuid4()), new=new)
        )


@tagged("post_install", "-at_install")
class TestAutonomousInteractive(InteractiveCase):
    def test_native_form_package_binding_and_no_manual_completion(self):
        version = self.version()
        with Form(self.env["slide.channel"].with_user(self.manager), view="training_elearning.course_form") as form:
            form.name = "Fictional native interactive course form"
            form.training_course_id = self.catalog
            with form.slide_ids.new() as activity:
                activity.name = "Fictional native interactive lesson"
                activity.slide_category = "learning_interactive"
                activity.learning_interactive_version_id = version
                activity.is_published = True
        course = form.record
        slide = course.slide_ids
        course.action_learning_publish()
        member = self.member(course)
        self.assertEqual(member.learning_plan["slides"][0]["version"], version.id)
        with self.assertRaises(AccessError):
            self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, slide.id)
        with self.assertRaises(AccessError):
            slide.with_user(self.learner)._action_mark_completed()
        self.assertEqual(member.completion, 0)

    def test_resume_idempotent_save_new_empty_attempt_and_first_acquisition_survives_lower_score(self):
        _course, slide, _version, member = self.interactive()
        key = str(uuid4())
        attempt = self.start(member, slide, key=key)
        self.assertEqual(self.start(member, slide, key=key), attempt)
        self.assertEqual(self.start(member, slide), attempt)
        event = {"state": {"page": "PRIVATE RESUME"}, "result": {"score": 75, "maximum": 100, "completed": True}}
        receipt = attempt._save("first-result", 1, event)
        acquired_at = member.completion_date
        self.assertEqual(attempt._save("first-result", 1, event), receipt)
        self.assertEqual(member.completion, 100)
        self.assertEqual(attempt._snapshot()["state"], event["state"])
        with self.assertRaises(ValidationError):
            attempt._save("first-result", 1, {"state": {"page": "changed"}})
        with patch.object(fields.Datetime, "now", return_value=fields.Datetime.now() + timedelta(hours=1)):
            later = self.start(member, slide, new=True)
            self.assertEqual(later.number, 2)
            self.assertEqual(later._snapshot()["state"], {})
            later._save("lower-result", 1, {"result": {"score": 1, "maximum": 100, "completed": True}})
        self.assertEqual(member.completion, 100)
        self.assertEqual(member.completion_date, acquired_at)
        with self.assertRaises(ValidationError):
            attempt._save("stale-new-event", 2, {"state": {}})

    def test_projection_failure_rolls_back_event_revision_and_native_leaf(self):
        _course, slide, _version, member = self.interactive()
        attempt = self.start(member, slide)
        payload = {"result": {"score": 100, "maximum": 100, "completed": True}}
        with patch.object(
            type(member), "_learning_sync_progress", side_effect=ValidationError("Fictional projection failure")
        ):
            with self.assertRaises(ValidationError):
                attempt._save("atomic-result", 1, payload)
        self.assertEqual(attempt.sudo().revision, 0)
        self.assertFalse(self.env["training.elearning.interactive.event"].search([("attempt_id", "=", attempt.id)]))
        self.assertEqual(member.completion, 0)
        self.assertFalse(
            self.env["slide.slide.partner"].search(
                [("slide_id", "=", slide.id), ("partner_id", "=", self.learner.partner_id.id), ("completed", "=", True)]
            )
        )
        self.assertTrue(attempt._save("atomic-result", 1, payload)["ok"])
        self.assertEqual(member.completion, 100)

    def test_whole_h5p_result_scope_expiration_withdrawal_and_capabilities(self):
        _course, slide, version, member = self.interactive("h5p")
        attempt = self.start(member, slide)
        with self.assertRaises(ValidationError):
            attempt._save("partial", 1, {"result": {"score": 0.5, "maximum": 1, "completed": True}})
        self.assertEqual(attempt.sudo().revision, 0)
        with self.assertRaises(AccessError):
            attempt.with_user(self.other)._snapshot()
        with self.assertRaises(AccessError):
            attempt.read(["state_json"])
        params = self.env["ir.config_parameter"]
        params.set_str("training_elearning.portal_origin", "https://portal.example.invalid")
        params.set_str("training_elearning.content_origin", "https://content.example.invalid")
        lease, token = self.env["training.elearning.lease"].with_user(self.learner)._issue(version, attempt)
        self.assertFalse(lease._is_preview())
        self.assertEqual(lease._content_snapshot()["state"], {})
        self.assertEqual(self.env["training.elearning.lease"]._resolve(token), lease)
        attempt._save("whole", 1, {"result": {"score": 1, "maximum": 1, "completed": True}})
        with patch.object(fields.Datetime, "now", return_value=member.learning_ends_at):
            with self.assertRaises(AccessError):
                attempt._snapshot()
            with self.assertRaises(AccessError):
                lease._renew()
        version.with_user(self.librarian)._withdraw("Fictional bounded content retirement")
        with self.assertRaises(AccessError):
            self.env["training.elearning.lease"]._resolve(token)
        with self.assertRaises(AccessError):
            attempt._save("retired", 2, {"state": {}})
        self.assertEqual(member.completion, 100)

    def test_revision_preserves_started_member_and_new_member_uses_new_version_and_threshold(self):
        course, slide, first, member = self.interactive()
        second = self.version(resource=first.resource_id, number="2")
        self.env["training.elearning.interactive.revision"].with_user(self.manager).create(
            {
                "slide_id": slide.id,
                "version_id": second.id,
                "threshold": 80,
                "reason": "Fictional evaluated content revision",
            }
        ).action_apply()
        self.assertEqual(member.learning_plan["slides"][0]["version"], first.id)
        self.assertEqual(self.start(member, slide).sudo().version_id, first)
        later = self.member(course, self.other)
        self.assertEqual(later.learning_plan["slides"][0]["version"], second.id)
        self.assertEqual(later.learning_plan["slides"][0]["threshold"], 80)
        with self.assertRaises(ValidationError):
            slide.write({"learning_interactive_rule": "completed"})
        self.assertTrue(slide.learning_interactive_revision_log)


@tagged("post_install", "-at_install")
class TestAutonomousInteractivePortal(InteractiveCase, HttpCase):
    def setUp(self):
        super().setUp()
        self.portal_origin = "http://127.0.0.1:%s" % self.http_port()
        self.content_origin = "http://localhost:%s" % self.http_port()
        params = self.env["ir.config_parameter"]
        params.set_str("training_elearning.portal_origin", self.portal_origin)
        params.set_str("training_elearning.content_origin", self.content_origin)

    def test_shared_player_scoped_bytes_atomic_save_and_expired_history(self):
        import json
        import re

        _course, slide, version, member = self.interactive()
        self.authenticate(self.learner.login, self.learner.login)
        entry_url = "/my/learning/%s/interactive/%s" % (member.id, slide.id)
        page = self.url_open(entry_url)
        self.assertEqual(page.status_code, 200)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        self.assertEqual(self.url_open(entry_url + "/start", data={"request_key": str(uuid4())}).status_code, 400)
        parent = self.url_open(entry_url + "/start", data={"request_key": str(uuid4()), "csrf_token": csrf})
        self.assertEqual(parent.status_code, 200)
        config = json.loads(
            re.search(r'<script id="config" type="application/json">(.*?)</script>', parent.text).group(1)
        )
        source = re.search(r'<iframe[^>]+src="([^"]+)"', parent.text).group(1)
        launch = self.url_open(source)
        self.assertEqual(launch.status_code, 200)
        self.assertIn("media-src 'none'", launch.headers["Content-Security-Policy"])
        file_url = source.removesuffix("/launch") + "/file/index.html"
        self.assertEqual(self.url_open(file_url).content, b"<p>Fictional SCO</p>")
        payload = {
            "key": str(uuid4()),
            "revision": 1,
            "data": {
                "state": {"page": "PRIVATE RUNTIME STATE"},
                "result": {"score": 80, "maximum": 100, "completed": True},
            },
        }
        saved = self.url_open(config["save"], data={"csrf_token": config["csrf"], "payload": json.dumps(payload)})
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["ok"])
        self.assertEqual(member.completion, 100)
        self.assertIn("PRIVATE RUNTIME STATE", self.url_open(source).text)
        native_file = (
            self.env["training.elearning.file"]
            .sudo()
            .search([("version_id", "=", version.id), ("path", "=", "index.html")])
        )
        self.assertIn(
            self.url_open("/web/content?model=training.elearning.file&id=%s&field=data" % native_file.id).status_code,
            (403, 404),
        )
        self.authenticate(self.other.login, self.other.login)
        self.assertEqual(self.url_open("/my/learning-interactive/attempt/%s" % config["attempt"]).status_code, 404)
        self.assertEqual(self.url_open(entry_url).status_code, 404)
        self.authenticate(self.learner.login, self.learner.login)
        with patch.object(fields.Datetime, "now", return_value=member.learning_ends_at):
            history = self.url_open(entry_url)
            self.assertEqual(history.status_code, 200)
            self.assertIn("80 / 100", history.text)
            self.assertNotIn("PRIVATE RUNTIME STATE", history.text)
            hub = self.url_open("/my/learning/%s/history" % member.id)
            self.assertEqual(hub.status_code, 200)
            self.assertIn(entry_url, hub.text)
            self.assertNotIn("PRIVATE RUNTIME STATE", hub.text)
            self.assertEqual(self.url_open("/my/learning-interactive/attempt/%s" % config["attempt"]).status_code, 404)
            self.assertIn(self.url_open(file_url).status_code, (403, 404))
