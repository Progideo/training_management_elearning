"""Versioned native practical work, atomic deposits and role-limited private files."""

import io
import re
import zipfile
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch
from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged
from .test_activities import LessonCase
from ..models.submission_files import InvalidSubmission, validate_files


@tagged("post_install", "-at_install")
class TestDefaultViews(TransactionCase):
    def test_company_defaults_and_upload_policy_action(self):
        views = self.env["ir.ui.view"]
        policy_list = self.env.ref("training_elearning.upload_policy_list")
        policy_form = self.env.ref("training_elearning.upload_policy_form")
        self.assertEqual(views.default_view("res.company", "form"), self.env.ref("base.view_company_form").id)
        self.assertNotEqual(views.default_view("res.company", "list"), policy_list.id)
        self.assertEqual(
            self.env.ref("training_elearning.upload_policy_action").views,
            [[policy_list.id, "list"], [policy_form.id, "form"]],
        )


class PracticalCase(LessonCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pedagogy = new_test_user(
            cls.env,
            login="fictional_practical_pedagogy",
            groups="training_elearning.group_elearning_pedagogy_manager",
        )

    def task(self, course, criterion="deposit", **values):
        task = (
            self.env["training.elearning.practical"]
            .with_user(self.manager)
            .create(
                {
                    "name": "Fictional private practical",
                    "training_course_id": self.catalog.id,
                    "criterion": criterion,
                    "instructions": "PRIVATE FICTIONAL INSTRUCTIONS",
                    **values,
                }
            )
        )
        task.action_publish()
        slide = (
            self.env["slide.slide"]
            .with_user(self.manager)
            .create(
                {
                    "channel_id": course.id,
                    "learning_practical_id": task.id,
                    "is_published": True,
                }
            )
        )
        return slide, task

    def deposit(self, member, slide, files=None, key=None):
        return (
            self.env["training.elearning.practical.service"]
            .with_user(self.learner)
            ._deposit(
                member.id,
                slide.id,
                files or [("fictional.txt", b"PRIVATE FICTIONAL SUBMISSION")],
                key or str(uuid4()),
            )
        )


@tagged("post_install", "-at_install")
class TestPracticalWork(PracticalCase):
    def test_native_declarations_deposits_and_repeat_requests(self):
        course = self.course()
        declaration, _self = self.task(course, "self")
        deposit, _task = self.task(course)
        course.action_learning_publish()
        member = self.member(course)
        self.assertEqual(course.nbr_learning_task, 2)
        self.assertEqual(deposit.nbr_learning_task, 0)
        generic = self.env["training.elearning.service"].with_user(self.learner)
        practical = self.env["training.elearning.practical.service"].with_user(self.learner)
        with self.assertRaises(AccessError):
            generic._declare(member.id, declaration.id)
        with self.assertRaises(AccessError):
            practical._declare(member.id, deposit.id)
        practical._declare(member.id, declaration.id)
        self.assertEqual(member.completion, 50)
        with self.assertRaises(AccessError):
            practical._deposit(member.id, declaration.id, [("x.txt", b"fictional")], str(uuid4()))
        with self.assertRaises(ValidationError):
            self.deposit(member, deposit, [("fake.pdf", b"not a PDF")])
        self.assertFalse(self.env["training.elearning.submission"].search([("membership_id", "=", member.id)]))
        self.assertEqual(member.completion, 50)
        key = str(uuid4())
        row = self.deposit(member, deposit, key=key)
        self.assertEqual(member.completion, 100)
        acquired = member.completion_date
        self.assertEqual(self.deposit(member, deposit, key=key), row)
        second = self.deposit(member, deposit)
        self.assertNotEqual(second, row)
        self.assertEqual(member.completion_date, acquired)
        self.assertEqual(row.payload_id.file_ids.raw.content, b"PRIVATE FICTIONAL SUBMISSION")
        self.assertEqual(row.payload_id.file_evidence[str(row.payload_id.file_ids.id)]["size"], 28)
        with self.assertRaises(AccessError):
            row.with_user(self.manager).action_private_payload()
        self.assertEqual(row.with_user(self.pedagogy).action_private_payload()["res_id"], row.payload_id.id)
        with self.assertRaises(AccessError):
            row.payload_id.with_user(self.manager).read(["file_evidence"])
        with self.assertRaises(AccessError):
            row.payload_id.file_ids.with_user(self.pedagogy).write({"raw": b"changed"})
        with self.assertRaises(AccessError):
            row.payload_id.file_ids.with_user(self.pedagogy).unlink()
        member._learning_store({"learning_ends_at": fields.Datetime.now() - timedelta(seconds=1)})
        self.assertEqual(self.deposit(member, deposit, key=key), row)
        self.assertEqual(practical._history(row.id), row.sudo())
        with self.assertRaises(AccessError):
            self.deposit(member, deposit)
        with self.assertRaises(AccessError):
            practical.with_user(self.other)._history(row.id)

    def test_published_versions_and_old_members_keep_their_contract(self):
        course = self.course()
        slide, first = self.task(course)
        course.action_learning_publish()
        member = self.member(course)
        with self.assertRaises(ValidationError):
            first.write({"instructions": "Changed"})
        with self.assertRaises(ValidationError):
            slide.write({"learning_practical_id": False})
        second = (
            self.env["training.elearning.practical"]
            .with_user(self.manager)
            .browse(first.action_new_version()["res_id"])
        )
        second.write(
            {
                "version_ref": "2",
                "revision_reason": "Fictional clearer instructions",
                "instructions": "Fictional revised instructions",
            }
        )
        second.action_publish()
        self.env["training.elearning.practical.revision"].with_user(self.manager).create(
            {
                "slide_id": slide.id,
                "practical_id": second.id,
                "reason": "Fictional selected revision",
            }
        ).action_apply()
        newer = self.member(course, self.other)
        self.assertEqual(member.learning_plan["slides"][0]["task"], first.id)
        self.assertEqual(newer.learning_plan["slides"][0]["task"], second.id)
        self.assertEqual(self.deposit(member, slide).practical_id, first)
        self.assertTrue(slide.learning_practical_revision_log)
        with self.assertRaises(AccessError):
            first.with_user(self.other).action_new_version()
        with self.assertRaises(AccessError):
            self.env["training.elearning.practical"].with_user(self.manager).with_context(
                default_origin_id=first.id
            ).create(
                {
                    "name": "Forged",
                    "training_course_id": self.catalog.id,
                    "instructions": "Fictional",
                }
            )

    def test_policies_formats_and_limits_are_checked_before_evidence(self):
        policy = {"extensions": "pdf,txt,csv,png,docx,json,xml", "files": 2, "file_mib": 1, "total_mib": 1}
        from PIL import Image
        from odoo.tools.pdf import PdfFileWriter

        pdf = io.BytesIO()
        writer = PdfFileWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(pdf)
        self.assertTrue(validate_files([("fictional.pdf", pdf.getvalue())], policy))
        png = io.BytesIO()
        Image.new("RGB", (64, 64), (40, 80, 160)).save(png, format="PNG")
        self.assertEqual(validate_files([("fictional.png", png.getvalue())], policy)[0]["content"], png.getvalue())
        self.assertTrue(validate_files([("large-cell.csv", b"x" * 150000)], policy))
        for files in (
            [("../x.txt", b"x")],
            [("x.txt", b"\x00")],
            [("x.png", b"not an image")],
            [("x.txt", b"x" * (1024 * 1024 + 1))],
            [("x.json", b"{")],
            [("x.xml", b'<!DOCTYPE x [<!ENTITY x "x">]><x/>')],
        ):
            with self.subTest(files=[name for name, _data in files]), self.assertRaises(InvalidSubmission):
                validate_files(files, policy)
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr(
                "[Content_Types].xml",
                '<Types><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
            )
            archive.writestr(
                "_rels/.rels",
                '<Relationships><Relationship Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
            )
            archive.writestr("word/document.xml", "<document/>")
        self.assertTrue(validate_files([("fictional.docx", package.getvalue())], policy))
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr("word/vbaProject.bin", b"fictional macro")
        with self.assertRaises(InvalidSubmission):
            validate_files([("fictional.docx", package.getvalue())], policy)
        with self.assertRaises(AccessError):
            self.env.company.with_user(self.manager).write({"learning_submission_max_files": 99})
        course = self.course()
        with self.assertRaises(ValidationError):
            self.task(course, max_files=999)


@tagged("post_install", "-at_install")
class TestPracticalPortal(PracticalCase, HttpCase):
    def test_private_multipart_csrf_tokens_and_personal_history_after_expiry(self):
        course = self.course()
        slide, _task = self.task(course)
        course.action_learning_publish()
        member = self.member(course)
        self.authenticate(self.learner.login, self.learner.login)
        path = f"/my/learning/{member.id}/tasks/{slide.id}"
        page = self.url_open(path)
        self.assertEqual(page.status_code, 200)
        self.assertIn("PRIVATE FICTIONAL INSTRUCTIONS", page.text)
        self.assertEqual(self.url_open(path + "/deposit", data={"request_key": str(uuid4())}).status_code, 400)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
        key = re.search(r'name="request_key" value="([^"]+)"', page.text)[1]
        response = self.url_open(
            path + "/deposit",
            data={"csrf_token": csrf, "request_key": key},
            files={"files": ("fictional.txt", b"PRIVATE FICTIONAL SUBMISSION", "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Mon rendu conservé", response.text)
        row = self.env["training.elearning.submission"].search([("membership_id", "=", member.id)])
        file = row.payload_id.file_ids
        self.assertEqual(len(file), 1)
        download = f"/my/learning-submissions/{row.id}/files/{file.id}"
        self.assertEqual(self.url_open(download).content, b"PRIVATE FICTIONAL SUBMISSION")
        # Simulate a leaked legacy bearer token/public bit outside the guarded ORM.
        self.env.cr.execute(
            "UPDATE ir_attachment SET public=true, access_token=%s WHERE id=%s", ["fictional-leaked", file.id]
        )
        file.invalidate_recordset()
        for user in (self.learner, self.manager, self.other):
            self.authenticate(user.login, user.login)
            response = self.url_open(f"/web/content/{file.id}?access_token=fictional-leaked")
            self.assertIn(response.status_code, (403, 404))
            self.assertNotIn(b"PRIVATE FICTIONAL SUBMISSION", response.content)
        self.assertEqual(self.url_open(download).status_code, 404)
        self.authenticate(self.learner.login, self.learner.login)
        with patch.object(fields.Datetime, "now", return_value=member.learning_ends_at + timedelta(seconds=1)):
            self.assertEqual(self.url_open(path).status_code, 404)
            history = self.url_open(f"/my/learning/{member.id}/history")
            self.assertEqual(history.status_code, 200)
            self.assertIn(f"/my/learning-submissions/{row.id}", history.text)
            self.assertNotIn("PRIVATE FICTIONAL INSTRUCTIONS", history.text)
            self.assertIn("Mon historique pédagogique", self.url_open(f"/my/learning/{member.id}").text)
            response = self.url_open(download)
            self.assertEqual(response.content, b"PRIVATE FICTIONAL SUBMISSION")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
