"""Real native PDFs, explicit consent, immutable replacements and live owner boundaries."""

import hashlib
import io
from datetime import timedelta
from unittest.mock import patch
from odoo import fields, Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, Form, new_test_user, tagged
from odoo.tools.pdf import PdfReader
from .test_path import PathCase


class CertificateCase(PathCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pedagogy = new_test_user(
            cls.env,
            login="fictional_certificate_coordinator",
            groups="training_elearning.group_elearning_pedagogy_manager",
        )

    def consent(self, member=None, registration=None, reactivate=None, accept=True):
        service = self.env["training.elearning.certificate.service"].with_user(self.learner)
        consent = service._prepare(
            membership_id=member.id if member else None,
            registration_id=registration.id if registration else None,
            reactivation_id=reactivate.id if reactivate else None,
        )
        consent._decide(accept)
        return consent

    def completed_course(self):
        course, slide = self.edition("Fictional certificate edition")
        member = self.member(course)
        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, slide.id)
        return course, slide, member

    def issued(self):
        _course, _slide, member = self.completed_course()
        consent = self.consent(member)
        acquired_at = member.completion_date
        document = consent.with_user(self.pedagogy)._issue()
        self.assertEqual(member.completion_date, acquired_at)
        return member, consent, document


@tagged("post_install", "-at_install")
class TestLearningCertificates(CertificateCase):
    def test_consent_does_not_complete_course_and_real_pdf_is_immutable(self):
        course, slide = self.edition("Fictional consent before achievement")
        member = self.member(course)
        refused = self.consent(member, accept=False)
        self.assertEqual(member.completion, 0)
        with self.assertRaises(ValidationError):
            refused.with_user(self.pedagogy)._issue()
        accepted = self.consent(member)
        with self.assertRaises(ValidationError):
            accepted.with_user(self.pedagogy)._issue()
        with self.assertRaises(AccessError):
            accepted.with_user(self.manager)._issue()
        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, slide.id)
        document = accepted.with_user(self.pedagogy)._issue()
        self.assertEqual(accepted.with_user(self.pedagogy)._issue(), document)
        self.assertEqual(len(document.token), 43)
        raw = document.pdf.content
        self.assertTrue(raw.startswith(b"%PDF-"))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), document.sha256)
        pdf = PdfReader(io.BytesIO(raw))
        self.assertEqual(len(pdf.pages), 1)
        text = pdf.pages[0].extract_text()
        self.assertIn(document.reference, text)
        self.assertIn("achèvement", text)
        self.assertNotIn("PRIVATE LESSON TEXT", text)
        links = [
            annotation.get_object().get("/A", {}).get("/URI")
            for page in pdf.pages
            for annotation in page.get("/Annots", [])
        ]
        self.assertIn(document.url, links)
        with self.assertRaises(AccessError):
            document.write({"pdf": False})
        with self.assertRaises(AccessError):
            document.copy()
        with self.assertRaises(AccessError):
            document.with_user(self.learner).read(["pdf"])

    def test_refusal_allows_achievement_without_automatic_document(self):
        course, slide = self.edition("Fictional declined certificate")
        member = self.member(course)
        refused = self.consent(member, accept=False)
        self.env["training.elearning.service"].with_user(self.learner)._declare(member.id, slide.id)
        self.assertEqual(member.completion, 100)
        self.assertTrue(member.completion_date)
        self.assertEqual(refused.state, "refused")
        self.assertFalse(self.env["training.elearning.certificate"].search([("membership_id", "=", member.id)]))
        self.assertEqual(self.consent(member).state, "accepted")

    def test_owner_disable_reactivation_requires_new_consent_and_valid_document(self):
        _member, _consent, document = self.issued()
        owner = self.env["training.elearning.certificate.service"].with_user(self.learner)
        public = self.env["training.elearning.certificate.service"]
        self.assertEqual(set(public._public(document.token)), {"holder_name", "title", "state"})
        old = document.pdf.content
        owner._own_document(document.id)._disable_public("Fictional holder request", owner=True)
        self.assertIsNone(public._public(document.token))
        self.assertEqual(owner._view(document.id)["state"], "valid")
        refused = self.consent(reactivate=document, accept=False)
        self.assertFalse(document.public_enabled)
        self.assertEqual(refused.state, "refused")
        self.consent(reactivate=document)
        self.assertTrue(document.public_enabled)
        self.assertEqual(document.pdf.content, old)
        document._change("withdrawn", "PRIVATE FICTIONAL WITHDRAWAL REASON")
        self.assertEqual(public._public(document.token)["state"], "withdrawn")
        self.assertNotIn("PRIVATE FICTIONAL", str(public._public(document.token)))
        owner._own_document(document.id)._disable_public("Fictional holder withdrawal privacy", owner=True)
        with self.assertRaises(ValidationError):
            self.consent(reactivate=document)

    def test_replacement_needs_fresh_matching_preview_and_keeps_old_bytes_and_url(self):
        member, _consent, first = self.issued()
        old, old_url = first.pdf.content, first.url
        self.learner.partner_id.name = "Fictional corrected holder"
        consent = self.consent(member)
        with self.assertRaises(ValidationError):
            consent.with_user(self.pedagogy)._issue()
        with Form(
            self.env["training.elearning.certificate.replace"]
            .with_user(self.pedagogy)
            .with_context(default_consent_id=consent.id)
        ) as form:
            form.reason = "Fictional corrected holder replacement"
        action = form.record.action_apply()
        second = self.env["training.elearning.certificate"].browse(action["res_id"])
        self.assertEqual(first.state, "replaced")
        self.assertEqual(first.replacement_id, second)
        self.assertNotEqual(first.token, second.token)
        self.assertNotEqual(first.pdf.content, second.pdf.content)
        self.assertEqual(first.pdf.content, old)
        self.assertEqual(first.url, old_url)
        projection = self.env["training.elearning.certificate.service"]._public(first.token)
        self.assertEqual(projection["state"], "replaced")
        self.assertNotIn(second.url, str(projection))

    def test_changed_identity_and_foreign_coordinator_are_rejected(self):
        _course, _slide, member = self.completed_course()
        consent = self.consent(member)
        self.learner.partner_id.name = "Fictional identity changed after consent"
        with self.assertRaises(ValidationError):
            consent.with_user(self.pedagogy)._issue()
        with self.assertRaises(AccessError):
            consent.with_user(self.pedagogy)._decide(True)
        foreign = self.env["res.company"].create({"name": "Fictional certificate foreign operator"})
        coordinator = new_test_user(
            self.env,
            login="fictional_foreign_certificate_coordinator",
            groups="training_elearning.group_elearning_pedagogy_manager",
            company_id=foreign.id,
            company_ids=[Command.set(foreign.ids)],
        )
        with self.assertRaises(AccessError):
            consent.with_user(coordinator)._issue()
        with self.assertRaises(AccessError):
            self.env["training.elearning.certificate.service"].with_user(self.other)._preview(consent.id)

    def test_path_certificate_requires_all_required_native_courses_and_survives_expiration(self):
        first, a = self.edition("Fictional attested path first")
        second, b = self.edition("Fictional attested path second")
        optional, _c = self.edition("Fictional attested path optional")
        path = self.path([(first, True), (second, True), (optional, False)])
        activation = self.activation(path)
        registration = activation.registration_id
        consent = self.consent(registration=registration)
        service = self.env["training.elearning.service"].with_user(self.learner)
        service._declare(registration._member(first.id).id, a.id)
        with self.assertRaises(ValidationError):
            consent.with_user(self.pedagogy)._issue()
        service._declare(registration._member(second.id).id, b.id)
        document = consent.with_user(self.pedagogy)._issue()
        with patch.object(fields.Datetime, "now", return_value=activation.starts_until + timedelta(days=500)):
            self.assertEqual(
                self.env["training.elearning.certificate.service"].with_user(self.learner)._view(document.id)["state"],
                "valid",
            )
        self.assertEqual(registration._member(optional.id).completion, 0)


@tagged("post_install", "-at_install")
class TestLearningCertificatePortal(CertificateCase, HttpCase):
    def test_http_consent_pdf_minimal_verification_and_disabled_non_disclosure(self):
        import re

        _course, _slide, member = self.completed_course()
        self.authenticate(self.learner.login, self.learner.login)
        source = self.url_open("/my/learning/%s" % member.id)
        token = re.search(r'name="csrf_token" value="([^"]+)"', source.text).group(1)
        self.assertEqual(
            self.url_open("/my/learning-certificates/prepare", data={"membership_id": member.id}).status_code, 400
        )
        preview = self.url_open(
            "/my/learning-certificates/prepare", data={"membership_id": member.id, "csrf_token": token}
        )
        self.assertEqual(preview.status_code, 200)
        self.assertIn("Toute personne possédant ce lien", preview.text)
        consent_id = int(preview.url.rstrip("/").rsplit("/", 1)[1])
        decide = "/my/learning-certificates/consent/%s/decide" % consent_id
        self.assertEqual(self.url_open(decide, data={"decision": "accept", "csrf_token": token}).status_code, 200)
        consent = self.env["training.elearning.certificate.consent"].browse(consent_id)
        document = consent.with_user(self.pedagogy)._issue()
        own_url = "/my/learning-certificates/%s/file" % document.id
        pdf = self.url_open(own_url)
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.content, document.pdf.content)
        self.assertIn("no-store", pdf.headers["Cache-Control"])
        native = "/web/content?model=training.elearning.certificate&id=%s&field=pdf&download=1" % document.id
        self.assertIn(self.url_open(native).status_code, (403, 404))
        native_report = "/report/pdf/training_elearning.certificate_pdf/%s" % document.id
        self.assertIn(self.url_open(native_report).status_code, (403, 404))
        self.authenticate(self.other.login, self.other.login)
        self.assertEqual(self.url_open(own_url).status_code, 404)
        self.assertEqual(self.url_open("/my/learning-certificates/consent/%s" % consent.id).status_code, 404)
        self.assertEqual(self.url_open("/training/learning-certificates/%s/file" % document.id).status_code, 404)
        self.authenticate(None, None)
        public_url = "/learning/certificates/%s" % document.token
        public = self.url_open(public_url)
        self.assertEqual(public.status_code, 200)
        self.assertIn(document.holder_name, public.text)
        self.assertIn("noindex", public.headers["X-Robots-Tag"])
        self.assertNotIn(document.reference, public.text)
        self.assertNotIn(document.sha256, public.text)
        self.assertNotIn(self.learner.partner_id.email, public.text)
        self.assertNotIn("PRIVATE LESSON", public.text)
        self.authenticate(self.learner.login, self.learner.login)
        own = self.url_open("/my/learning-certificates")
        token = re.search(r'name="csrf_token" value="([^"]+)"', own.text).group(1)
        self.assertEqual(
            self.url_open("/my/learning-certificates/%s/disable" % document.id, data={"csrf_token": token}).status_code,
            200,
        )
        self.authenticate(None, None)
        unavailable = self.url_open(public_url)
        self.assertIn("Vérification indisponible", unavailable.text)
        self.assertNotIn(document.holder_name, unavailable.text)
        self.assertNotIn(document.title, unavailable.text)


@tagged("post_install", "-at_install")
class TestLearningCertificateNotices(CertificateCase):
    def test_actual_send_entrypoint_cancels_stale_recipient_and_keeps_document(self):
        _member, consent, document = self.issued()
        notices = self.env["training.elearning.certificate.notice"].search([("certificate_id", "=", document.id)])
        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.state, "queued")
        mail = notice.mail_id
        self.assertFalse(mail.attachment_ids)
        self.assertFalse(mail.email_to)
        self.assertFalse(mail.email_cc)
        self.assertEqual(mail.recipient_ids, self.learner.partner_id)
        self.assertNotIn(document.token, str(mail.body_html))
        self.assertEqual(consent.with_user(self.pedagogy)._issue(), document)
        self.assertEqual(
            self.env["training.elearning.certificate.notice"].search_count([("certificate_id", "=", document.id)]), 1
        )
        mail.sudo().write({"recipient_ids": [Command.set(self.other.partner_id.ids)]})
        mail.sudo()._send()
        self.assertEqual(mail.state, "cancel")
        self.assertEqual(notice.state, "cancelled")
        self.assertEqual(document.state, "valid")

    def test_delivery_incident_retry_closes_activity_only_after_observed_native_success(self):
        _member, _consent, document = self.issued()
        notice = self.env["training.elearning.certificate.notice"].search([("certificate_id", "=", document.id)])
        mail = notice.mail_id
        with self.assertRaises(AccessError):
            mail.with_user(self.learner).write({"state": "sent"})
        mail.sudo().write({"state": "exception"})
        notice._sync()
        self.assertEqual(notice.state, "exception")
        self.assertTrue(notice.incident_activity_id)
        notice.with_user(self.pedagogy).action_retry()
        self.assertEqual(mail.state, "outgoing")
        self.assertTrue(notice.incident_activity_id)
        # Confined synthetic native transition; SMTP is disabled in Odoo tests.
        mail.sudo().write({"state": "sent"})
        notice._sync()
        self.assertEqual(notice.state, "sent")
        self.assertFalse(notice.incident_activity_id)
