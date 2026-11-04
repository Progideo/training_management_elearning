# pylint: disable=super-method-mismatch,method-required-super,context-overridden
"""Explicit consent, manual issue and immutable native PDF certificates independent of TM."""

import base64
import hashlib
import secrets
from uuid import uuid4
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import BinaryBytes
from .human_practical import PEDAGOGY


def staff(record):
    user = record.env.user
    if (
        not record
        or not user.active
        or not user.has_group(PEDAGOGY)
        or any(
            company not in user.company_ids or company not in record.env.companies
            for company in record.sudo().company_id
        )
    ):
        raise AccessError(record.env._("An authorized pedagogical coordinator in this company is required."))
    record.with_env(record.env(su=False)).check_access("read")


def source_values(record):
    source = record.sudo()
    if source.membership_id:
        member = source.membership_id
        progress = member._learning_progress()
        return {
            "name": member.partner_id.name,
            "title": member.channel_id.name,
            "complete": progress["complete"],
            "completed_at": member.completion_date,
        }
    registration = source.registration_id
    progress = registration._summary()
    return {
        "name": registration.partner_id.name,
        "title": registration.path_id.name,
        "complete": progress["complete"],
        "completed_at": progress["completed_at"],
    }


class Consent(models.Model):
    _name = "training.elearning.certificate.consent"
    _description = "Explicit Learning Certificate Consent"
    _rec_name = "holder_name"
    company_id = fields.Many2one("res.company", required=True, readonly=True, ondelete="restrict")
    user_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    membership_id = fields.Many2one("slide.channel.partner", readonly=True, ondelete="restrict")
    registration_id = fields.Many2one("training.elearning.path.registration", readonly=True, ondelete="restrict")
    reactivation_id = fields.Many2one("training.elearning.certificate", readonly=True, ondelete="restrict")
    holder_name = fields.Char(required=True, readonly=True)
    title = fields.Char(required=True, readonly=True)
    state = fields.Selection(
        [("draft", "Prévisualisation"), ("accepted", "Acceptée"), ("refused", "Refusée")],
        default="draft",
        readonly=True,
    )
    decided_at = fields.Datetime(readonly=True)
    certificate_id = fields.Many2one("training.elearning.certificate", readonly=True, ondelete="restrict")

    _source_required = models.Constraint(
        "CHECK ((membership_id IS NOT NULL) <> (registration_id IS NOT NULL))",
        "Choose exactly one course or curriculum source.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Prepare the personal certificate preview through the learner workspace."))

    def write(self, values):
        raise AccessError(self.env._("Keep the explicit certificate consent trace."))

    @api.ondelete(at_uninstall=False)
    def _keep_consent(self):
        raise AccessError(self.env._("Keep certificate consent history."))

    @api.private
    def _store(self, values):
        return super(Consent, self.sudo()).write(values)

    @api.private
    def _create_preview(self, values):
        return super(Consent, self.sudo().with_context({})).create(values)

    @api.private
    def _lock_source(self):
        self.ensure_one()
        if self.membership_id:
            self.sudo().membership_id.channel_id.lock_for_update()
        else:
            self.sudo().registration_id.path_id.lock_for_update()
        source = self.sudo().membership_id or self.sudo().registration_id
        source.lock_for_update()
        if self.sudo().registration_id:
            registration = self.sudo().registration_id
            members = (
                self.env["slide.channel.partner"]
                .sudo()
                .with_context(active_test=False)
                .search(
                    [
                        ("channel_id", "in", [item["course"] for item in registration.composition]),
                        ("partner_id", "=", registration.partner_id.id),
                        ("learning_user_id", "=", registration.user_id.id),
                    ]
                )
            )
            members.channel_id.sorted("id").lock_for_update()
            members.sorted("id").lock_for_update()
            members.invalidate_recordset()
        self.lock_for_update()
        self.invalidate_recordset()

    @api.private
    def _decide(self, accepted):
        self.ensure_one()
        self.env["training.elearning.certificate.service"]._own_consent(self.id)
        self._lock_source()
        state = "accepted" if accepted else "refused"
        if self.state != "draft":
            if self.state != state:
                raise ValidationError(self.env._("Prepare a new preview to record a different consent decision."))
            return True
        with self.env.cr.savepoint():
            self._store({"state": state, "decided_at": fields.Datetime.now()})
            if accepted and self.reactivation_id:
                self.reactivation_id._enable_public(self)
        return True

    def action_issue(self):
        self.ensure_one()
        document = self._issue()
        return {
            "type": "ir.actions.act_window",
            "res_model": document._name,
            "res_id": document.id,
            "view_mode": "form",
        }

    def action_prepare_replacement(self):
        self.ensure_one()
        staff(self)
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.certificate.replace",
            "view_mode": "form",
            "target": "new",
            "context": {"default_consent_id": self.id},
        }

    @api.private
    def _issue(self, replacement_reason=None):
        with self.env.cr.savepoint():
            return self._issue_locked(replacement_reason=replacement_reason)

    @api.private
    def _issue_locked(self, replacement_reason=None):
        self.ensure_one()
        staff(self)
        self._lock_source()
        if self.certificate_id:
            return self.certificate_id
        if self.state != "accepted" or not self.decided_at or self.reactivation_id:
            raise ValidationError(self.env._("The holder must explicitly accept this document preview before issue."))
        if not self.user_id.active or self.company_id not in self.user_id.company_ids:
            raise AccessError(self.env._("The named holder must remain active in this operating company."))
        source = source_values(self)
        if not source["complete"] or (source["name"], source["title"]) != (self.holder_name, self.title):
            raise ValidationError(
                self.env._(
                    "Complete the applicable obligations and obtain a fresh consent if the displayed identity changed."
                )
            )
        # A lock alone does not advance a repeatable-read snapshot. Touch a
        # technical revision on the canonical source before checking for an
        # existing certificate, so a stale competing consent must retry.
        (self.membership_id or self.registration_id)._certificate_touch()
        documents = self.env["training.elearning.certificate"].sudo()
        domain = [("state", "=", "valid"), ("user_id", "=", self.user_id.id)]
        domain += (
            [("membership_id", "=", self.membership_id.id)]
            if self.membership_id
            else [("registration_id", "=", self.registration_id.id)]
        )
        previous = documents.search(domain, limit=1)
        if previous and not (replacement_reason or "").strip():
            raise ValidationError(self.env._("A valid certificate already exists; use a motivated replacement."))
        if replacement_reason and not previous:
            raise ValidationError(self.env._("Choose a valid certificate to replace."))
        token = secrets.token_urlsafe(32)
        url = f"{self.get_base_url().rstrip('/')}/learning/certificates/{token}"
        snapshot = {
            "holder_name": self.holder_name,
            "title": self.title,
            "issuer": self.company_id.name,
            "issued_at": fields.Datetime.to_string(fields.Datetime.now()),
            "completed_at": fields.Datetime.to_string(source["completed_at"]),
            "reference": "EL-" + uuid4().hex[:16].upper(),
            "template": "J13-QWEB-1",
            "url": url,
        }
        engine = self.env["ir.actions.report"]
        report = self.env.ref("training_elearning.report_certificate")
        html = engine._render_template(
            "training_elearning.certificate_pdf",
            {
                "values": snapshot,
                "qr": "data:image/png;base64,"
                + base64.b64encode(engine.barcode("QR", url, width=240, height=240)).decode(),
            },
        ).decode()
        raw = engine._run_pdf_engine_without_processing(engine._get_pdf_engine(report), [html], report_ref=report)
        if not raw.startswith(b"%PDF-"):
            raise ValidationError(self.env._("The native PDF engine did not produce a valid certificate."))
        if previous:
            previous._change("replaced", replacement_reason)
            previous.flush_recordset(["state"])
        document = documents._create_issued(
            {
                "consent_id": self.id,
                "company_id": self.company_id.id,
                "user_id": self.user_id.id,
                "membership_id": self.membership_id.id,
                "registration_id": self.registration_id.id,
                "holder_name": self.holder_name,
                "title": self.title,
                "reference": snapshot["reference"],
                "token": token,
                "url": url,
                "snapshot": snapshot,
                "pdf": BinaryBytes(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "issued_at": fields.Datetime.to_datetime(snapshot["issued_at"]),
                "issued_by": self.env.uid,
                "public_enabled": True,
            }
        )
        if previous:
            previous._store({"replacement_id": document.id})
        self._store({"certificate_id": document.id})
        if not previous:
            document._notify("issued")
        return document


class Certificate(models.Model):
    _name = "training.elearning.certificate"
    _description = "Immutable Learning Completion Certificate"
    _rec_name = "reference"
    consent_id = fields.Many2one(
        "training.elearning.certificate.consent", required=True, readonly=True, ondelete="restrict"
    )
    company_id = fields.Many2one("res.company", required=True, readonly=True, ondelete="restrict")
    user_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    membership_id = fields.Many2one("slide.channel.partner", readonly=True, ondelete="restrict")
    registration_id = fields.Many2one("training.elearning.path.registration", readonly=True, ondelete="restrict")
    holder_name = fields.Char(required=True, readonly=True)
    title = fields.Char(required=True, readonly=True)
    reference = fields.Char(required=True, readonly=True)
    token = fields.Char(required=True, readonly=True, groups=PEDAGOGY)
    url = fields.Char(required=True, readonly=True, groups=PEDAGOGY)
    snapshot = fields.Json(required=True, readonly=True, groups=PEDAGOGY)
    pdf = fields.Binary(attachment=False, readonly=True, groups=PEDAGOGY)
    sha256 = fields.Char(required=True, readonly=True)
    issued_at = fields.Datetime(required=True, readonly=True)
    issued_by = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    state = fields.Selection(
        [("valid", "Valide"), ("withdrawn", "Retirée"), ("replaced", "Remplacée")],
        default="valid",
        required=True,
        readonly=True,
    )
    reason = fields.Text(readonly=True, groups=PEDAGOGY)
    changed_at = fields.Datetime(readonly=True)
    changed_by = fields.Many2one("res.users", readonly=True, ondelete="restrict")
    replacement_id = fields.Many2one("training.elearning.certificate", readonly=True, ondelete="restrict")
    public_enabled = fields.Boolean(readonly=True)
    public_log = fields.Json(readonly=True, groups=PEDAGOGY)
    _source_required = models.Constraint(
        "CHECK ((membership_id IS NOT NULL) <> (registration_id IS NOT NULL))",
        "Choose exactly one course or curriculum source.",
    )
    _unique_consent = models.Constraint("UNIQUE(consent_id)", "This consent already has its issued document.")
    _unique_reference = models.Constraint("UNIQUE(reference)", "This certificate reference already exists.")
    _unique_token = models.Constraint("UNIQUE(token)", "This certificate token already exists.")
    _valid_course = models.UniqueIndex(
        "(membership_id) WHERE state = 'valid' AND membership_id IS NOT NULL",
        "This course already has a valid certificate.",
    )
    _valid_path = models.UniqueIndex(
        "(registration_id) WHERE state = 'valid' AND registration_id IS NOT NULL",
        "This curriculum already has a valid certificate.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Issue the certificate through its accepted preview."))

    def write(self, values):
        raise AccessError(self.env._("Keep issued PDFs and use the audited certificate actions."))

    def copy_data(self, default=None):
        raise AccessError(self.env._("Issued certificates cannot be copied."))

    @api.ondelete(at_uninstall=False)
    def _keep_document(self):
        raise AccessError(self.env._("Keep issued certificates and their history."))

    @api.private
    def _create_issued(self, values):
        return super(Certificate, self.sudo().with_context({})).create(values)

    @api.private
    def _store(self, values):
        return super(Certificate, self.sudo()).write(values)

    @api.private
    def _notify(self, kind):
        return True  # The notification adapter is registered separately.

    @api.private
    def _change(self, state, reason):
        staff(self)
        self.lock_for_update()
        self.invalidate_recordset()
        if self.state != "valid" or state not in ("withdrawn", "replaced") or not (reason or "").strip():
            raise ValidationError(self.env._("Change a valid certificate with a mandatory internal reason."))
        self._store(
            {"state": state, "reason": reason.strip(), "changed_at": fields.Datetime.now(), "changed_by": self.env.uid}
        )
        self._notify(state)
        return True

    @api.private
    def _disable_public(self, reason, *, owner=False):
        if owner:
            self.env["training.elearning.certificate.service"]._own_document(self.id)
        else:
            staff(self)
        self.lock_for_update()
        self.invalidate_recordset()
        if not (reason or "").strip():
            raise ValidationError(self.env._("Explain the public verification deactivation."))
        if self.public_enabled:
            log = list(self.sudo().public_log or [])
            log.append(
                {
                    "at": fields.Datetime.to_string(fields.Datetime.now()),
                    "actor": self.env.uid,
                    "enabled": False,
                    "reason": reason.strip(),
                }
            )
            self._store({"public_enabled": False, "public_log": log})
        return True

    @api.private
    def _enable_public(self, consent):
        self.lock_for_update()
        self.invalidate_recordset()
        if (
            self.state != "valid"
            or consent.reactivation_id != self
            or consent.state != "accepted"
            or consent.user_id != self.user_id
        ):
            raise AccessError(self.env._("A new explicit holder consent is required for a valid certificate."))
        if not self.public_enabled:
            log = list(self.sudo().public_log or [])
            log.append(
                {
                    "at": fields.Datetime.to_string(fields.Datetime.now()),
                    "actor": consent.user_id.id,
                    "enabled": True,
                    "consent": consent.id,
                }
            )
            self._store({"public_enabled": True, "public_log": log})

    def action_download(self):
        self.ensure_one()
        staff(self)
        return {
            "type": "ir.actions.act_url",
            "url": "/training/learning-certificates/%s/file" % self.id,
            "target": "self",
        }

    def action_change(self):
        self.ensure_one()
        staff(self)
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.certificate.change",
            "view_mode": "form",
            "target": "new",
            "context": {"default_certificate_id": self.id},
        }


class FrozenCertificateReport(models.AbstractModel):
    _name = "report.training_elearning.certificate_pdf"
    _description = "Guard Against Rerendering Issued Learning Certificates"

    @api.model
    def _get_report_values(self, docids, data=None):
        raise AccessError(self.env._("Download the immutable issued certificate through its checked private action."))


class CertificateMembership(models.Model):
    _inherit = "slide.channel.partner"
    learning_certificate_revision = fields.Integer(readonly=True, copy=False)

    @api.private
    def _certificate_touch(self):
        self._learning_store({"learning_certificate_revision": self.sudo().learning_certificate_revision + 1})
        self.flush_recordset(["learning_certificate_revision"])
