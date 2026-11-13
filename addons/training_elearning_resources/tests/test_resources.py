"""Fictional native Odoo 20 tests: bytes, grants, raw routes and frozen editions."""
import io
import zipfile
from datetime import timedelta
from PIL import Image
from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, HttpCase, new_test_user, tagged
from odoo.tools import BinaryBytes


def archive(workbook=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as package:
        package.writestr("[Content_Types].xml" if workbook else "exercises.txt", "Fictional exercises")
        if workbook:
            package.writestr("xl/workbook.xml", "<workbook/>")
    return output.getvalue()


def raster(kind, size=(2, 2)):
    output = io.BytesIO()
    Image.new("RGB", size, "red").save(output, format=kind)
    return output.getvalue()


class ResourceCase:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(cls.env, login="fictional_resource_manager",
                                   groups="training_elearning.group_elearning_manager")
        cls.owner = new_test_user(cls.env, login="fictional_resource_owner", groups="base.group_portal")
        cls.other = new_test_user(cls.env, login="fictional_resource_other", groups="base.group_portal")
        cls.catalog = cls.env["training.course"].create({"name": "Fictional resource catalogue"})

    def fixture(self):
        course = self.env["slide.channel"].with_user(self.manager).create({
            "name": "Fictional resource edition", "training_course_id": self.catalog.id})
        slide = self.env["slide.slide"].with_user(self.manager).create({
            "name": "Fictional activity", "channel_id": course.id, "slide_category": "article",
            "html_content": "<p>Fictional article</p>", "is_published": True})
        return course, slide

    def file(self, slide, name="exercises.zip", body=None):
        return self.env["slide.slide.resource"].with_user(self.manager).create({
            "slide_id": slide.id, "resource_type": "file", "name": name, "file_name": name,
            "data": BinaryBytes(body if body is not None else archive())})

    def activate(self, course):
        course.action_learning_publish()
        member = self.env["slide.channel.partner"].with_user(self.manager).create({
            "channel_id": course.id, "partner_id": self.owner.partner_id.id})
        member.action_learning_activate(fields.Datetime.now() + timedelta(days=365), self.owner.id, "Fictional access")
        return member

    def service(self, user=None):
        return self.env["training.elearning.resource.service"].with_user(user or self.owner)


@tagged("post_install", "-at_install")
class TestResources(ResourceCase, TransactionCase):
    def test_formats_exact_bytes_and_frozen_plan(self):
        course, slide = self.fixture()
        payloads = {"exercises.zip": archive(), "exercises.xlsx": archive(True),
                    "legacy.xls": bytes.fromhex("d0cf11e0a1b11ae1") + b"fictional workbook",
                    "image.png": raster("PNG"), "image.gif": raster("GIF"),
                    "image.jpg": raster("JPEG"), "image.jpeg": raster("JPEG"),
                    "large.png": raster("PNG", (2000, 20)), "large.jpg": raster("JPEG", (2000, 20))}
        resources = [self.file(slide, name, body) for name, body in payloads.items()]
        for resource in resources:
            resource.invalidate_recordset(["data"])
        member = self.activate(course)
        self.assertEqual(len(member.learning_plan["slides"][0]["resources"]), len(payloads))
        for resource in resources:
            current, snapshot = self.service()._context(member.id, slide.id, resource.id)
            self.assertEqual(current.with_context(bin_size=False).data.content, payloads[resource.file_name])
            self.assertEqual(snapshot["size"], len(payloads[resource.file_name]))
        self.assertEqual(member.completion, 0)
        self.assertEqual(len(self.service()._rows(member.id)[0]["entries"]), len(payloads))

    def test_account_deadline_revoke_prerequisites_and_wrong_resource(self):
        course, slide = self.fixture()
        resource = self.file(slide)
        member = self.activate(course)
        alternate = new_test_user(self.env, login="fictional_resource_same_contact", groups="base.group_portal",
                                  partner_id=self.owner.partner_id.id)
        for user in (self.other, alternate, self.env.ref("base.public_user")):
            with self.assertRaises(AccessError):
                self.service(user)._context(member.id, slide.id, resource.id)
        self.owner.active = False
        with self.assertRaises(AccessError):
            self.service()._context(member.id, slide.id, resource.id)
        self.owner.active = True
        _, other_slide = self.fixture()
        other_resource = self.file(other_slide)
        with self.assertRaises(AccessError):
            self.service()._context(member.id, slide.id, other_resource.id)
        member._learning_store({"learning_ends_at": fields.Datetime.now() - timedelta(seconds=1)})
        self.assertEqual(self.service()._rows(member.id), [])
        with self.assertRaises(AccessError):
            self.service()._context(member.id, slide.id, resource.id)
        member._learning_store({"learning_ends_at": fields.Datetime.now() + timedelta(days=2)})
        member.action_learning_revoke("Fictional revocation")
        with self.assertRaises(AccessError):
            self.service()._context(member.id, slide.id, resource.id)
        course, slide = self.fixture()
        prerequisite = self.env["slide.slide"].with_user(self.manager).create({
            "name": "Fictional prerequisite", "channel_id": course.id, "slide_category": "article",
            "html_content": "<p>Read first</p>", "is_published": True})
        slide.learning_prerequisite_ids = [Command.set(prerequisite.ids)]
        resource = self.file(slide)
        member = self.activate(course)
        with self.assertRaises(AccessError):
            self.service()._context(member.id, slide.id, resource.id)
        self.env["training.elearning.service"].with_user(self.owner)._declare(member.id, prerequisite.id)
        self.assertTrue(self.service()._context(member.id, slide.id, resource.id))

    def test_frozen_resource_and_attachment_cannot_be_mutated_or_reparented(self):
        course, slide = self.fixture()
        resource = self.file(slide)
        self.activate(course)
        _, other_slide = self.fixture()
        for values in ({"data": BinaryBytes(archive(True))}, {"name": "Changed"},
                       {"slide_id": other_slide.id}, {"sequence": 99}):
            with self.assertRaises(ValidationError):
                resource.write(values)
        with self.assertRaises(ValidationError):
            resource.unlink()
        with self.assertRaises(ValidationError):
            self.file(slide)
        attachment = self.env["ir.attachment"].with_user(self.manager).search([
            ("res_model", "=", "slide.slide.resource"), ("res_field", "=", "data"), ("res_id", "=", resource.id)])
        self.assertTrue(attachment)
        for values in ({"raw": b"changed"}, {"public": True}, {"access_token": "fictional-token"},
                       {"res_model": "res.partner", "res_id": self.manager.partner_id.id}):
            with self.assertRaises(ValidationError):
                attachment.write(values)
        with self.assertRaises(ValidationError):
            attachment.unlink()

    def test_raw_rpc_and_company_isolation_unmanaged_native_resources_unchanged(self):
        course, slide = self.fixture()
        resource = self.file(slide)
        member = self.activate(course)
        with self.assertRaises(AccessError):
            resource.with_user(self.owner).read(["data", "link"])
        self.assertFalse(self.env["slide.slide.resource"].with_user(self.owner).search([("id", "=", resource.id)]))
        with self.assertRaises(AccessError):
            self.env["ir.binary"].with_user(self.owner)._find_record(
                res_model="slide.slide.resource", res_id=resource.id, field="data")
        company = self.env["res.company"].create({"name": "Fictional other company"})
        self.manager.company_ids |= company
        with self.assertRaises(AccessError):
            resource.with_user(self.manager).with_context(allowed_company_ids=company.ids).read(["data"])
        self.owner.write({"company_id": company.id, "company_ids": [Command.set(company.ids)]})
        with self.assertRaises(AccessError):
            self.service().with_context(allowed_company_ids=company.ids)._context(member.id, slide.id, resource.id)
        native = self.env["slide.channel"].with_user(self.manager).create({"name": "Fictional unmanaged course"})
        lesson = self.env["slide.slide"].with_user(self.manager).create({
            "name": "Native activity", "channel_id": native.id, "slide_category": "article"})
        ordinary = self.env["slide.slide.resource"].with_user(self.manager).create({
            "slide_id": lesson.id, "resource_type": "url", "link": "https://example.invalid/native"})
        ordinary.write({"link": "https://example.invalid/updated"})
        self.assertEqual(ordinary.link, "https://example.invalid/updated")
        ordinary_image = self.file(lesson, "ordinary.png", raster("PNG", (2000, 20)))
        ordinary_image.invalidate_recordset(["data"])
        with Image.open(io.BytesIO(ordinary_image.data.content)) as image:
            self.assertEqual(image.width, 1920)  # Native unmanaged resize remains in force.

    def test_practical_resources_respect_availability_without_completing_work(self):
        course, _ = self.fixture()
        task = self.env["training.elearning.practical"].with_user(self.manager).create({
            "name": "Fictional practical resource", "training_course_id": self.catalog.id,
            "criterion": "self", "instructions": "Fictional exercise instructions"})
        task.action_publish()
        slide = self.env["slide.slide"].with_user(self.manager).create({
            "channel_id": course.id, "learning_practical_id": task.id, "is_published": True})
        resource = self.file(slide)
        member = self.activate(course)
        self.assertTrue(self.service()._context(member.id, slide.id, resource.id))
        self.assertEqual(member.completion, 0)
        slide.action_learning_change_availability("Fictional temporary withdrawal")
        with self.assertRaises(AccessError):
            self.service()._context(member.id, slide.id, resource.id)
        self.assertEqual(self.service()._rows(member.id), [])

    def test_invalid_types_links_and_private_attachment_flags(self):
        _, slide = self.fixture()
        for name, data in (("attack.html", b"<script/>"), ("../image.png", raster("PNG")),
                           ("fake.png", b"not PNG"), ("empty.zip", b""), ("fake.xlsx", archive()),
                           ("fake.xls", b"not Excel"), ("fake.jpg", raster("GIF"))):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self.file(slide, name, data)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.file(slide, "oversized.zip", b"x" * (64 * 1024 * 1024 + 1))
        for link in ("javascript:alert(1)", "//example.invalid", "https://user:pass@example.invalid", "https://example.invalid/\n"):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self.env["slide.slide.resource"].with_user(self.manager).create({
                    "slide_id": slide.id, "resource_type": "url", "link": link})
        resource = self.file(slide)
        attachment = self.env["ir.attachment"].with_user(self.manager).search([
            ("res_model", "=", "slide.slide.resource"), ("res_field", "=", "data"), ("res_id", "=", resource.id)])
        with self.assertRaises(ValidationError):
            attachment.write({"public": True})


@tagged("post_install", "-at_install")
class TestResourcesHTTP(ResourceCase, HttpCase):
    def test_contextual_download_page_redirect_and_native_route_refusals(self):
        course, slide = self.fixture()
        body = archive()
        resource = self.file(slide, "exercices été.zip", body)
        link = self.env["slide.slide.resource"].with_user(self.manager).create({
            "slide_id": slide.id, "name": "Fictional external site", "resource_type": "url",
            "link": "https://example.invalid/exercises"})
        extra_files = [(self.file(slide, name, payload), payload) for name, payload in (
            ("exercise.xlsx", archive(True)), ("exercise.xls", bytes.fromhex("d0cf11e0a1b11ae1") + b"fictional"),
            ("picture.png", raster("PNG")), ("picture.gif", raster("GIF")), ("picture.jpg", raster("JPEG")),
            ("large.png", raster("PNG", (2000, 20))), ("large.jpg", raster("JPEG", (2000, 20))))]
        member = self.activate(course)
        path = "/my/learning/%s/activities/%s/resources/%s" % (member.id, slide.id, resource.id)
        self.authenticate(self.owner.login, self.owner.login)
        response = self.url_open(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, body)
        self.assertIn("attachment;", response.headers["Content-Disposition"])
        self.assertEqual(response.headers["Content-Type"], "application/zip")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        for extra, payload in extra_files:
            download = self.url_open(path.rsplit("/", 1)[0] + "/%s" % extra.id)
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download.content, payload)
            self.assertIn("attachment;", download.headers["Content-Disposition"])
        self.assertIn(path, self.url_open("/my/learning/%s" % member.id).text)
        response = self.url_open(path.rsplit("/", 1)[0] + "/%s" % link.id, allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "https://example.invalid/exercises")
        attachment = self.env["ir.attachment"].sudo().search([
            ("res_model", "=", "slide.slide.resource"), ("res_field", "=", "data"), ("res_id", "=", resource.id)])
        self.assertEqual(len(attachment), 1)
        # Simulate a pre-existing native bearer URL: the new boundary must still
        # refuse it. SQL is deliberately confined to this fictional adversarial fixture.
        self.env.cr.execute("UPDATE ir_attachment SET public=true, access_token=%s WHERE id=%s",
                            ["fictional-legacy-token", attachment.id])
        attachment.invalidate_recordset()
        for raw in ("/web/content/slide.slide.resource/%s/data?download=true" % resource.id,
                    "/web/content/%s?download=true&access_token=fictional-legacy-token" % attachment.id):
            self.assertNotEqual(self.url_open(raw).content, body)
        self.authenticate(self.other.login, self.other.login)
        self.assertEqual(self.url_open(path).status_code, 404)
        self.authenticate(self.owner.login, self.owner.login)
        member._learning_store({"learning_ends_at": fields.Datetime.now() - timedelta(seconds=1)})
        self.assertEqual(self.url_open(path).status_code, 404)
        self.assertNotIn(path, self.url_open("/my/learning/%s" % member.id).text)
        self.authenticate(None, None)
        self.assertNotEqual(self.url_open(path, allow_redirects=False).status_code, 200)
        self.assertNotEqual(self.url_open("/web/content/%s?access_token=fictional-legacy-token" % attachment.id).content, body)
