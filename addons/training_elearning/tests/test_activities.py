"""Native lesson evidence and direct-link access, without Survey or Sales."""

import io
import re
from datetime import timedelta
from unittest.mock import patch
from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, HttpCase, Form, new_test_user, tagged
from odoo.tools import BinaryBytes
from odoo.tools.pdf import PdfFileWriter


class LessonCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env, login="fictional_lesson_manager", groups="training_elearning.group_elearning_manager"
        )
        cls.learner = new_test_user(cls.env, login="fictional_lesson_learner", groups="base.group_portal")
        cls.other = new_test_user(cls.env, login="fictional_lesson_other", groups="base.group_portal")
        cls.catalog = cls.env["training.course"].create({"name": "Fictional lesson catalogue"})

    def course(self, **vals):
        return (
            self.env["slide.channel"]
            .with_user(self.manager)
            .create({"name": "Fictional lesson edition", "training_course_id": self.catalog.id, **vals})
        )

    def article(self, course, **vals):
        return (
            self.env["slide.slide"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional private article",
                    "channel_id": course.id,
                    "slide_category": "article",
                    "html_content": "<p>PRIVATE LESSON TEXT</p>",
                    "is_published": True,
                    **vals,
                }
            )
        )

    def member(self, course, user=None):
        user = user or self.learner
        member = (
            self.env["slide.channel.partner"]
            .with_user(self.manager)
            .create({"channel_id": course.id, "partner_id": user.partner_id.id})
        )
        member.action_learning_activate(fields.Datetime.now() + timedelta(days=2), user.id, "Fictional grant")
        return member

    def pdf(self, course):
        output = io.BytesIO()
        writer = PdfFileWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(output)
        return (
            self.env["slide.slide"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional private PDF",
                    "channel_id": course.id,
                    "slide_category": "document",
                    "source_type": "local_file",
                    "binary_content": BinaryBytes(output.getvalue()),
                    "learning_filename": "fictional.pdf",
                    "is_published": True,
                }
            )
        )


@tagged("post_install", "-at_install")
class TestNativeLessons(LessonCase):
    def test_native_course_form_accepts_mixed_lesson_configuration(self):
        with Form(self.env["slide.channel"].with_user(self.manager), view="training_elearning.course_form") as form:
            form.name = "Fictional native lesson form"
            form.training_course_id = self.catalog
            with form.slide_ids.new() as lesson:
                lesson.name = "Fictional form article"
                lesson.slide_category = "article"
                lesson.html_content = "<p>Fictional native form content</p>"
                lesson.is_published = True
        course = form.record
        course.action_learning_publish()
        self.assertEqual(course.learning_state, "published")
        self.assertFalse(course.is_published)
        self.assertFalse(course.slide_ids.is_preview)

    def test_explicit_completion_native_leaf_optional_and_renewal(self):
        course = self.course()
        first = self.article(course)
        pdf = self.pdf(course)
        optional = self.article(course, name="Fictional optional article", learning_optional=True)
        course.action_learning_publish()
        member = self.member(course)
        service = self.env["training.elearning.service"].with_user(self.learner)
        service._activity(member.id, pdf.id)
        self.assertEqual(member.completion, 0)
        mail_count = self.env["mail.mail"].search_count([])
        service._declare(member.id, first.id)
        self.assertEqual(member.completion, 50)
        service._declare(member.id, first.id)
        self.assertEqual(
            self.env["slide.slide.partner"]
            .sudo()
            .search_count([("slide_id", "=", first.id), ("partner_id", "=", self.learner.partner_id.id)]),
            1,
        )
        service._declare(member.id, pdf.id)
        self.assertEqual(member.completion, 100)
        self.assertEqual(member.member_status, "completed")
        self.assertTrue(member.completion_date)
        self.assertFalse(service._item_status(member, optional._learning_plan_item())["complete"])
        self.assertEqual(self.env["mail.mail"].search_count([]), mail_count)
        plan = member.learning_plan
        acquired_at = member.completion_date
        future = fields.Datetime.now() + timedelta(days=1)
        with patch.object(fields.Datetime, "now", return_value=future):
            member.action_learning_activate(future + timedelta(days=3), self.learner.id, "Fictional renewal")
        self.assertEqual(member.completion_date, acquired_at)
        self.assertEqual(member.learning_plan, plan)
        self.assertEqual(member.completion, 100)
        with self.assertRaises(AccessError):
            service.with_user(self.other)._declare(member.id, pdf.id)
        with self.assertRaises(AccessError):
            self.env["slide.slide.partner"].with_context(learning_projection_in_progress=True).create(
                {"slide_id": optional.id, "partner_id": self.learner.partner_id.id, "completed": True}
            )

    def test_prerequisites_are_explicit_and_navigation_is_free_otherwise(self):
        previous = self.course(name="Fictional prerequisite edition")
        previous_slide = self.article(previous)
        previous.action_learning_publish()
        prior_member = self.member(previous)
        course = self.course(prerequisite_channel_ids=[Command.set(previous.ids)])
        first = self.article(course)
        locked = self.article(course, learning_prerequisite_ids=[Command.set(first.ids)])
        free = self.article(course)
        course.action_learning_publish()
        member = self.member(course)
        service = self.env["training.elearning.service"].with_user(self.learner)
        with self.assertRaises(AccessError):
            service._activity(member.id, free.id)
        service._declare(prior_member.id, previous_slide.id)
        prior_member._learning_store({"learning_ends_at": fields.Datetime.now() - timedelta(seconds=1)})
        service._activity(member.id, free.id)
        with self.assertRaises(AccessError):
            service._declare(member.id, locked.id)
        service._declare(member.id, first.id)
        service._declare(member.id, locked.id)
        self.assertEqual(member.completion, 67)
        member._learning_store({"learning_ends_at": fields.Datetime.now() - timedelta(seconds=1)})
        with self.assertRaises(AccessError):
            service._declare(member.id, free.id)
        self.assertEqual(service._membership(member.id, history=True), member.sudo())

    def test_graph_rejects_cycles_optional_required_and_foreign_lesson(self):
        course = self.course()
        first = self.article(course)
        second = self.article(course, learning_prerequisite_ids=[Command.set(first.ids)])
        first.write({"learning_prerequisite_ids": [Command.set(second.ids)]})
        with self.assertRaises(ValidationError):
            course.action_learning_publish()
        first.write({"learning_prerequisite_ids": [Command.clear()], "learning_optional": True})
        with self.assertRaises(ValidationError):
            course.action_learning_publish()
        first.write({"learning_optional": False})
        foreign = self.article(self.course())
        second.write({"learning_prerequisite_ids": [Command.set(foreign.ids)]})
        with self.assertRaises(ValidationError):
            course.action_learning_publish()
        second.write({"learning_prerequisite_ids": [Command.set(first.ids)]})
        course.action_learning_publish()
        other = self.course(prerequisite_channel_ids=[Command.set(course.ids)])
        self.article(other)
        other.action_learning_publish()
        course.write({"prerequisite_channel_ids": [Command.set(other.ids)]})
        with self.assertRaises(ValidationError):
            course.action_learning_publish()
        with self.assertRaises(ValidationError):
            self.member(course)

    def test_pdf_validation_and_video_intentionally_public(self):
        course = self.course()
        slide = (
            self.env["slide.slide"]
            .with_user(self.manager)
            .with_context(website_slides_skip_fetch_metadata=True)
            .create(
                {
                    "name": "Fictional video",
                    "channel_id": course.id,
                    "slide_category": "video",
                    "video_url": "https://www.youtube.com/watch?v=fictional01",
                    "is_published": True,
                }
            )
        )
        with self.assertRaises(ValidationError):
            course.action_learning_publish()
        slide.write({"learning_public_video": True})
        course.action_learning_publish()
        broken = self.course()
        self.env["slide.slide"].with_user(self.manager).create(
            {
                "name": "Fictional invalid PDF",
                "channel_id": broken.id,
                "slide_category": "document",
                "source_type": "local_file",
                "binary_content": BinaryBytes(b"not a PDF"),
                "is_published": True,
            }
        )
        with self.assertRaises(ValidationError):
            broken.action_learning_publish()

    def test_native_attachment_mutations_cannot_change_frozen_course_files(self):
        course = self.course()
        slide = self.pdf(course)
        course.action_learning_publish()
        self.member(course)
        file = (
            self.env["ir.attachment"]
            .with_user(self.manager)
            .search(
                [("res_model", "=", "slide.slide"), ("res_id", "=", slide.id), ("res_field", "=", "binary_content")]
            )
        )
        self.assertEqual(len(file), 1)
        original = file.raw.content
        for values in (
            {"raw": b"changed outside the course"},
            {"res_model": "res.partner", "res_id": self.manager.partner_id.id},
            {"public": True},
        ):
            with self.assertRaises(ValidationError):
                file.write(values)
        with self.assertRaises(ValidationError):
            file.unlink()
        with self.assertRaises(ValidationError):
            self.env["ir.attachment"].with_user(self.manager).with_context(
                default_res_model="slide.slide", default_res_id=slide.id
            ).create({"name": "Fictional late attachment", "raw": b"late"})
        other = (
            self.env["ir.attachment"]
            .with_user(self.manager)
            .create({"name": "Fictional unrelated attachment", "raw": b"unrelated"})
        )
        with self.assertRaises(ValidationError):
            other.write({"res_model": "slide.slide", "res_id": slide.id})
        self.assertEqual(file.raw.content, original)

    def test_started_dependent_binds_its_prerequisite_edition_and_new_copy_is_draft(self):
        parent = self.course(name="Fictional bound prerequisite")
        parent_slide = self.article(parent)
        parent.action_learning_publish()
        child = self.course(prerequisite_channel_ids=[Command.set(parent.ids)])
        self.article(child)
        child.action_learning_publish()
        self.member(child)
        self.assertTrue(parent.learning_bound_at)
        with self.assertRaises(ValidationError):
            parent_slide.write({"html_content": "<p>Changed prerequisite content</p>"})
        with self.assertRaises(AccessError):
            parent.write({"learning_bound_at": False})
        edition = parent.copy({"name": "Fictional next substantive edition"})
        self.assertFalse(edition.learning_bound_at)
        self.assertEqual(edition.learning_state, "draft")
        self.assertFalse(edition.channel_partner_ids)
        self.assertEqual(edition.training_course_id, parent.training_course_id)

    def test_company_identity_and_snapshot_are_protected(self):
        course = self.course()
        slide = self.article(course)
        course.action_learning_publish()
        member = self.member(course)
        with self.assertRaises(AccessError):
            member.write({"learning_plan": {"slides": []}})
        with self.assertRaises(ValidationError):
            slide.write({"learning_optional": True})
        foreign = self.env["res.company"].create({"name": "Fictional other operator"})
        with self.assertRaises(ValidationError):
            self.catalog.write({"company_id": foreign.id})
        self.assertEqual(member.learning_plan["slides"][0]["id"], slide.id)


@tagged("post_install", "-at_install")
class TestNativeLessonPortal(LessonCase, HttpCase):
    def test_article_images_are_owned_sanitized_and_not_bearer_links(self):
        course = self.course()
        slide = self.article(course)
        other_slide = self.article(course)
        # Native image upload on a lesson, with a deliberately public flag.
        image = (
            self.env["ir.attachment"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional image",
                    "res_model": "slide.slide",
                    "res_id": slide.id,
                    "raw": b"fictional-raster",
                    "mimetype": "image/png",
                    "public": True,
                }
            )
        )
        foreign = (
            self.env["ir.attachment"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional other lesson image",
                    "res_model": "slide.slide",
                    "res_id": other_slide.id,
                    "raw": b"fictional-other-raster",
                    "mimetype": "image/png",
                }
            )
        )
        slide.write(
            {
                "html_content": '<p>Fictional article</p><img src="/web/image/%s?access_token=untrusted"/><img src="/web/image/%s"/><iframe src="https://example.invalid/untrusted"></iframe>'
                % (image.id, foreign.id)
            }
        )
        course.action_learning_publish()
        member = self.member(course)
        self.authenticate(self.learner.login, self.learner.login)
        path = "/my/learning/%s/activities/%s" % (member.id, slide.id)
        page = self.url_open(path)
        self.assertEqual(page.status_code, 200)
        self.assertIn(path + "/images/%s" % image.id, page.text)
        self.assertNotIn("access_token=untrusted", page.text)
        self.assertNotIn("example.invalid", page.text)
        self.assertNotIn(path + "/images/%s" % foreign.id, page.text)
        self.assertEqual(self.url_open(path + "/images/%s" % image.id).content, b"fictional-raster")
        self.assertEqual(self.url_open(path + "/images/%s" % foreign.id).status_code, 404)
        # Native image routes can return a public placeholder after refusal.
        self.assertNotEqual(self.url_open("/web/image/%s" % image.id).content, image.raw.content)
        self.authenticate(self.other.login, self.other.login)
        self.assertEqual(self.url_open(path + "/images/%s" % image.id).status_code, 404)

    def test_pending_editorial_upload_is_private_even_with_native_attachment_token(self):
        course = self.course()
        slide = self.pdf(course)
        course.action_learning_publish()
        self.member(course)
        wizard = (
            self.env["training.elearning.editorial"]
            .with_user(self.manager)
            .create(
                {
                    "course_id": course.id,
                    "slide_id": slide.id,
                    "name": slide.name,
                    "category": "accessibility",
                    "reason": "Fictional pending editorial file",
                }
            )
        )
        file = (
            self.env["ir.attachment"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional private editorial upload",
                    "res_model": "training.elearning.editorial",
                    "res_id": wizard.id,
                    "raw": b"PRIVATE PENDING EDITORIAL BYTES",
                    "public": True,
                }
            )
        )
        token = file.generate_access_token()[0]
        self.authenticate(self.learner.login, self.learner.login)
        response = self.url_open("/web/content/%s?access_token=%s" % (file.id, token))
        self.assertIn(response.status_code, (403, 404))
        self.assertNotIn(b"PRIVATE PENDING EDITORIAL BYTES", response.content)

    def test_motivated_pdf_closure_blocks_previously_authorized_private_download(self):
        course = self.course()
        slide = self.pdf(course)
        course.action_learning_publish()
        member = self.member(course)
        self.authenticate(self.learner.login, self.learner.login)
        path = "/my/learning/%s/activities/%s/pdf" % (member.id, slide.id)
        self.assertEqual(self.url_open(path).status_code, 200)
        slide.action_learning_change_availability("Fictional private PDF closure")
        self.assertEqual(self.url_open(path).status_code, 404)
        self.assertEqual(self.url_open("/my/learning/%s" % member.id).status_code, 200)
        slide.action_learning_change_availability("Fictional PDF reopened", reopen=True)
        self.assertEqual(self.url_open(path).status_code, 200)

    def test_private_files_direct_prerequisite_csrf_and_expiry(self):
        course = self.course()
        first = self.article(course)
        pdf = self.pdf(course)
        pdf.write({"learning_prerequisite_ids": [Command.set(first.ids)]})
        course.action_learning_publish()
        member = self.member(course)
        self.authenticate(self.learner.login, self.learner.login)
        root = "/my/learning/%s" % member.id
        page = self.url_open(root)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.url_open("%s/activities/%s/pdf" % (root, pdf.id)).status_code, 404)
        activity = "%s/activities/%s" % (root, first.id)
        page = self.url_open(activity)
        self.assertIn("PRIVATE LESSON TEXT", page.text)
        self.assertEqual(member.completion, 0)
        self.assertEqual(self.url_open(activity + "/complete", data={"confirm": "1"}).status_code, 400)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
        self.assertEqual(self.url_open(activity + "/complete", data={"csrf_token": csrf}).status_code, 200)
        response = self.url_open("%s/activities/%s/pdf" % (root, pdf.id))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(member.completion, 50)
        self.assertIn(self.url_open("/web/content/slide.slide/%s/binary_content" % pdf.id).status_code, (403, 404))
        self.authenticate(self.other.login, self.other.login)
        self.assertEqual(self.url_open(activity).status_code, 404)
        self.assertEqual(self.url_open("%s/activities/%s/pdf" % (root, pdf.id)).status_code, 404)
        self.authenticate(self.learner.login, self.learner.login)
        with patch.object(fields.Datetime, "now", return_value=member.learning_ends_at + timedelta(seconds=1)):
            self.assertEqual(self.url_open(activity).status_code, 404)
            self.assertEqual(self.url_open("%s/activities/%s/pdf" % (root, pdf.id)).status_code, 404)
            self.assertEqual(self.url_open(root).status_code, 200)
