"""Audited cosmetic updates use native fields without resetting learner evidence."""

import io
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, tagged
from odoo.tools import BinaryBytes
from odoo.tools.pdf import PdfFileWriter
from .test_activities import LessonCase


@tagged("post_install", "-at_install")
class TestEditorialCorrections(LessonCase):
    def test_native_form_traces_article_and_course_corrections_without_changing_acquisitions(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        member = self.member(course)
        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, slide.id)
        completed_at, plan = member.completion_date, member.learning_plan
        action = slide.action_learning_editorial()
        with Form(
            self.env["training.elearning.editorial"].with_user(self.manager).with_context(**action["context"])
        ) as form:
            form.category = "typo"
            form.reason = "Fictional correction of a spelling mistake"
            form.name = "Fictional corrected article title"
            form.html_content = "<p>PRIVATE CORRECTED ARTICLE</p>"
        form.record.action_apply()
        self.assertEqual(member.completion, 100)
        self.assertEqual(member.completion_date, completed_at)
        self.assertEqual(member.learning_plan, plan)
        self.assertEqual(member._learning_plan()["slides"][0]["title"], slide.name)
        self.assertEqual(slide.learning_editorial_log[0]["actor"], self.manager.id)
        changes = slide.learning_editorial_log[0]["changes"]
        self.assertNotEqual(changes["html_content"]["before"], changes["html_content"]["after"])
        self.assertNotIn("PRIVATE CORRECTED ARTICLE", str(changes))
        with self.assertRaises(ValidationError):
            slide.write({"html_content": "<p>Untraced replacement</p>"})
        with self.assertRaises(AccessError):
            slide.write({"learning_editorial_log": False})
        course._learning_apply_editorial(
            {"name": "Fictional corrected edition title"}, "Fictional presentation typo", "typo"
        )
        self.assertEqual(course.learning_editorial_log[0]["actor"], self.manager.id)
        self.assertEqual(member.completion, 100)
        self.assertTrue(course.message_ids.filtered(lambda m: "Fictional presentation typo" in (m.body or "")))
        with self.assertRaises(AccessError):
            course.write({"learning_editorial_log": False})

    def test_pdf_uses_native_binary_path_and_restores_the_guard_after_success_or_failure(self):
        course = self.course()
        slide = self.pdf(course)
        course.action_learning_publish()
        member = self.member(course)
        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, slide.id)
        acquired_at = member.completion_date
        output = io.BytesIO()
        writer = PdfFileWriter()
        writer.addBlankPage(width=200, height=200)
        writer.add_metadata({"/Title": "Fictional accessible title"})
        writer.write(output)
        old_content = slide.binary_content.content
        slide._learning_apply_editorial(
            {"binary_content": BinaryBytes(output.getvalue()), "learning_filename": "fictional-accessible.pdf"},
            "Fictional accessibility metadata",
            "accessibility",
        )
        self.assertNotEqual(slide.binary_content.content, old_content)
        self.assertEqual(slide.binary_content.content, output.getvalue())
        self.assertEqual(member.completion, 100)
        self.assertEqual(member.completion_date, acquired_at)
        file = (
            self.env["ir.attachment"]
            .with_user(self.manager)
            .search(
                [("res_model", "=", "slide.slide"), ("res_id", "=", slide.id), ("res_field", "=", "binary_content")]
            )
        )
        for actor in (
            file,
            file.with_context(learning_editorial_scope=(self.manager.id, slide.id), learning_revision=True),
        ):
            with self.assertRaises(ValidationError):
                actor.write({"raw": b"untraced"})
        with self.assertRaises(ValidationError):
            slide._learning_apply_editorial(
                {"binary_content": BinaryBytes(b"invalid PDF")}, "Fictional invalid replacement", "accessibility"
            )
        self.assertEqual(slide.binary_content.content, output.getvalue())
        self.assertEqual(len(slide.learning_editorial_log), 1)
        with self.assertRaises(ValidationError):
            file.write({"raw": b"scope must be closed after exception"})

    def test_editorial_action_cannot_change_obligations_prerequisites_or_foreign_courses(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        self.member(course)
        for values in (
            {"learning_optional": True},
            {"learning_prerequisite_ids": [Command.clear()]},
            {"channel_id": self.course().id},
        ):
            with self.assertRaises(ValidationError):
                slide._learning_apply_editorial(values, "Fictional inadmissible semantic change", "typo")
        with self.assertRaises(AccessError):
            slide.with_user(self.learner)._learning_apply_editorial(
                {"name": "Forged"}, "Fictional unprivileged request", "typo"
            )
        with self.assertRaises(ValidationError):
            slide._learning_apply_editorial({"name": slide.name}, "Fictional unchanged value", "typo")
        self.assertFalse(slide.learning_editorial_log)
