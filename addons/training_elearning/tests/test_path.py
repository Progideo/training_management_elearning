"""Curricula aggregate native courses, reuse exact editions and open eligible courses once."""

from datetime import timedelta
from unittest.mock import patch
from dateutil.relativedelta import relativedelta
from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, Form, tagged
from .test_activities import LessonCase
from .test_human_practical import HumanCase


class PathCase(LessonCase):
    def edition(self, name, prerequisites=None):
        course = self.course(
            name=name,
            prerequisite_channel_ids=[Command.set((prerequisites or self.env["slide.channel"]).ids)],
        )
        article = self.article(course)
        course.action_learning_publish()
        return course, article

    def path(self, lines):
        path = (
            self.env["training.elearning.path"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional native curriculum",
                    "line_ids": [
                        Command.create({"course_id": course.id, "required": required}) for course, required in lines
                    ],
                }
            )
        )
        path.action_publish()
        return path

    def activation(self, path, courses=None):
        return (
            self.env["training.elearning.path.activation"]
            .with_user(self.manager)
            ._activate(
                path,
                self.learner.partner_id,
                path._plan(courses.ids if courses is not None else None),
                6,
                12,
                "Fictional explicit curriculum authorization",
            )
        )


@tagged("post_install", "-at_install")
class TestNativePaths(PathCase):
    def test_parallel_required_courses_optional_course_and_form_replay(self):
        first, a = self.edition("Fictional first parallel course")
        second, b = self.edition("Fictional second parallel course")
        optional, _c = self.edition("Fictional optional course")
        path = self.path([(first, True), (second, True), (optional, False)])
        with Form(
            self.env["training.elearning.path.activate"].with_user(self.manager).with_context(default_path_id=path.id)
        ) as form:
            form.partner_id = self.learner.partner_id
            form.reason = "Fictional manual native form authorization"
        wizard = form.record
        action = wizard.action_activate()
        context = self.env["training.elearning.path.activation"].browse(action["res_id"])
        self.assertEqual(len(context.item_ids.filtered("activated_at")), 3)
        ends = context.item_ids.mapped("access_ends_at")
        mails = self.env["training.elearning.path.notice"].search_count([("activation_id", "=", context.id)])
        self.assertEqual(wizard.action_activate()["res_id"], context.id)
        self.assertEqual(context.item_ids.mapped("access_ends_at"), ends)
        self.assertEqual(
            self.env["training.elearning.path.notice"].search_count([("activation_id", "=", context.id)]),
            mails,
        )
        registration = context.registration_id
        self.assertEqual(registration._summary()["percentage"], 0)
        service = self.env["training.elearning.service"].with_user(self.learner)
        service._declare(registration._member(first.id).id, a.id)
        self.assertEqual(registration._summary()["percentage"], 50)
        service._declare(registration._member(second.id).id, b.id)
        self.assertTrue(registration._summary()["complete"])
        self.assertEqual(registration._summary()["percentage"], 100)
        self.assertEqual(registration._member(optional.id).completion, 0)
        self.assertTrue(registration._summary()["completed_at"])
        with self.assertRaises(ValidationError):
            path.line_ids[:1].write({"required": False})
        with self.assertRaises(AccessError):
            registration.write({"composition": []})

    def test_chain_full_duration_personal_renewal_keeps_start_limit_and_late_adjustment(
        self,
    ):
        first, a = self.edition("Fictional prerequisite course")
        second, b = self.edition("Fictional dependent course", first)
        third, _c = self.edition("Fictional final course", second)
        path = self.path([(first, True), (second, True), (third, True)])
        context = self.activation(path)
        registered = context.registration_id
        opened = context.item_ids.filtered("activated_at")
        self.assertEqual(opened.course_id, first)
        limit = context.starts_until
        month11 = context.activated_at + relativedelta(months=11)
        with patch.object(fields.Datetime, "now", return_value=month11):
            # Explicit renewal of the individual course does not move the path limit.
            member = registered._member(first.id)
            member.with_user(self.manager).action_learning_activate(
                month11 + relativedelta(months=6),
                self.learner.id,
                "Fictional personal course renewal",
            )
            self.assertEqual(context.starts_until, limit)
            self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, a.id)
            item = context.item_ids.filtered(lambda row: row.course_id == second)
            self.assertEqual(item.activated_at, month11)
            self.assertEqual(item.access_ends_at, month11 + relativedelta(months=6))
        after = limit + timedelta(hours=1)
        with patch.object(fields.Datetime, "now", return_value=after):
            self.env["training.elearning.service"].with_user(self.learner)._declare(
                registered._member(second.id).id, b.id
            )
            final = context.item_ids.filtered(lambda row: row.course_id == third)
            self.assertFalse(final.activated_at)
            self.env["training.elearning.path.item"]._cron_path_starts()
            self.assertFalse(final.activated_at)
            context.with_user(self.manager)._adjust(
                after + timedelta(days=2),
                "Fictional traced late prerequisite adjustment",
            )
            self.assertEqual(final.activated_at, after)
            self.assertEqual(final.access_ends_at, after + relativedelta(months=6))
            self.assertTrue(context.adjustment_log)

    def test_exact_edition_acquisition_reuse_without_reopening_unfunded_course(self):
        first, a = self.edition("Fictional prior acquired edition")
        prior = self.member(first)
        self.env["training.elearning.service"].with_user(self.learner)._declare(prior.id, a.id)
        expired = fields.Datetime.now() - timedelta(seconds=1)
        prior._learning_store({"learning_ends_at": expired})
        second, _b = self.edition("Fictional newly funded course", first)
        other_edition, _c = self.edition("Fictional other edition of same catalogue")
        path = self.path([(first, True), (second, True), (other_edition, False)])
        context = self.activation(path, second)
        self.assertEqual(context.item_ids.course_id, second)
        self.assertTrue(context.item_ids.activated_at)
        self.assertEqual(prior.learning_ends_at, expired)
        self.assertEqual(context.registration_id._summary()["percentage"], 50)
        self.assertFalse(context.registration_id._member(other_edition.id))
        with self.assertRaises(AccessError):
            self.env["training.elearning.service"].with_user(self.learner)._activity(prior.id, a.id)

    def test_optional_course_cannot_become_required_indirectly(self):
        first, _a = self.edition("Fictional optional prerequisite")
        second, _b = self.edition("Fictional required dependent", first)
        with self.assertRaises(ValidationError):
            self.path([(first, False), (second, True)])


@tagged("post_install", "-at_install")
class TestHumanPathProgress(HumanCase):
    def test_late_human_validation_opens_next_course_with_full_duration(self):
        first, task_slide, _task, member = self.human()
        second = self.course(
            name="Fictional next course after human judgement",
            prerequisite_channel_ids=[Command.set(first.ids)],
        )
        self.article(second)
        second.action_learning_publish()
        path = (
            self.env["training.elearning.path"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional human prerequisite curriculum",
                    "line_ids": [Command.create({"course_id": course.id}) for course in first | second],
                }
            )
        )
        path.action_publish()
        context = (
            self.env["training.elearning.path.activation"]
            .with_user(self.manager)
            ._activate(
                path,
                self.learner.partner_id,
                path._plan(),
                6,
                12,
                "Fictional authorized human prerequisite path",
            )
        )
        queue = self.deposit(member, task_slide).review_queue_id
        late = member.learning_ends_at + timedelta(hours=1)
        with patch.object(fields.Datetime, "now", return_value=late):
            self.publish(queue, outcome="validated", passed=True)
            item = context.item_ids.filtered(lambda row: row.course_id == second)
            self.assertEqual(item.activated_at, late)
            self.assertEqual(item.access_ends_at, late + relativedelta(months=6))
            self.assertEqual(context.registration_id._summary()["percentage"], 50)


@tagged("post_install", "-at_install")
class TestPathPortal(PathCase, HttpCase):
    def test_personal_path_context_and_native_tokens_remain_private(self):
        first, _a = self.edition("Fictional private curriculum course")
        path = self.path([(first, True)])
        file = (
            self.env["ir.attachment"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional private path presentation",
                    "res_model": path._name,
                    "res_id": path.id,
                    "raw": b"PRIVATE CURRICULUM ATTACHMENT",
                    "public": True,
                }
            )
        )
        token = file.generate_access_token()[0]
        context = self.activation(path)
        self.authenticate(self.learner.login, self.learner.login)
        page = self.url_open(f"/my/learning-paths/{context.registration_id.id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Fictional native curriculum", page.text)
        self.assertIn("Mes parcours autonomes", self.url_open("/my").text)
        response = self.url_open(f"/web/content/{file.id}?access_token={token}")
        self.assertIn(response.status_code, (403, 404))
        self.assertNotIn(b"PRIVATE CURRICULUM ATTACHMENT", response.content)
        self.authenticate(self.other.login, self.other.login)
        self.assertEqual(
            self.url_open(f"/my/learning-paths/{context.registration_id.id}").status_code,
            404,
        )
        with self.assertRaises(AccessError):
            self.env["training.elearning.path.registration"].with_user(self.other).search([])
