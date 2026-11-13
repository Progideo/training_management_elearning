"""Owner-only certificate previews, history and minimal public verification projections."""

import re
from odoo import api, models
from odoo.exceptions import AccessError, ValidationError
from .certificate import source_values


class Service(models.AbstractModel):
    _name = "training.elearning.certificate.service"
    _description = "Private Learning Certificate Workspace"

    @api.private
    def _owner(self, record):
        user = self.env.user
        if (
            not record
            or not user.active
            or user._is_public()
            or record.user_id != user
            or record.company_id not in user.company_ids
        ):
            raise AccessError(self.env._("This personal certificate context is unavailable."))
        source = record.membership_id or record.registration_id
        source_user = source.learning_user_id if record.membership_id else source.user_id
        if source.partner_id != user.partner_id or source_user != user:
            raise AccessError(self.env._("This account no longer matches the original certificate holder."))
        return record

    @api.private
    def _own_document(self, document_id):
        return self._owner(self.env["training.elearning.certificate"].sudo().browse(document_id).exists())

    @api.private
    def _own_consent(self, consent_id):
        return self._owner(self.env["training.elearning.certificate.consent"].sudo().browse(consent_id).exists())

    @api.private
    def _prepare(self, *, membership_id=None, registration_id=None, reactivation_id=None):
        if sum(bool(value) for value in (membership_id, registration_id, reactivation_id)) != 1:
            raise ValidationError(self.env._("Choose exactly one personal certificate context."))
        document = self.env["training.elearning.certificate"]
        member = self.env["slide.channel.partner"]
        registration = self.env["training.elearning.path.registration"]
        if reactivation_id:
            document = self._own_document(reactivation_id)
            if document.state != "valid" or document.public_enabled:
                raise ValidationError(
                    self.env._("Only a valid certificate with disabled verification can be reactivated.")
                )
            member, registration = document.membership_id, document.registration_id
        elif membership_id:
            member = self.env["training.elearning.service"]._membership(membership_id, history=True)
        else:
            registration = self.env["training.elearning.path.service"]._registration(registration_id)
        user = self.env.user
        values = {
            "company_id": (member.channel_id.learning_company_id if member else registration.company_id).id,
            "user_id": user.id,
            "membership_id": member.id,
            "registration_id": registration.id,
            "reactivation_id": document.id,
            "holder_name": document.holder_name if document else user.partner_id.name,
            "title": document.title if document else member.channel_id.name if member else registration.path_id.name,
        }
        return self.env["training.elearning.certificate.consent"]._create_preview(values)

    @api.private
    def _preview(self, consent_id):
        consent = self._own_consent(consent_id)
        return {
            "id": consent.id,
            "holder_name": consent.holder_name,
            "title": consent.title,
            "state": consent.state,
            "decided_at": consent.decided_at,
            "reactivation": bool(consent.reactivation_id),
            "complete": source_values(consent)["complete"],
        }

    @api.private
    def _view(self, document_id):
        document = self._own_document(document_id)
        return {
            "id": document.id,
            "holder_name": document.holder_name,
            "title": document.title,
            "reference": document.reference,
            "state": document.state,
            "issued_at": document.issued_at,
            "public_enabled": document.public_enabled,
            "url": document.url,
            "sha256": document.sha256,
        }

    @api.private
    def _list(self):
        documents = (
            self.env["training.elearning.certificate"]
            .sudo()
            .search([("user_id", "=", self.env.uid)], order="issued_at desc,id desc")
        )
        result = []
        for document in documents:
            try:
                result.append(self._view(document.id))
            except AccessError:
                continue
        return result

    @api.private
    def _consents(self):
        rows = (
            self.env["training.elearning.certificate.consent"]
            .sudo()
            .search([("user_id", "=", self.env.uid)], order="id desc")
        )
        result = []
        for row in rows:
            try:
                result.append(self._preview(row.id))
            except AccessError:
                continue
        return result

    @api.private
    def _public(self, token):
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token or ""):
            return None
        document = (
            self.env["training.elearning.certificate"]
            .sudo()
            .search([("token", "=", token), ("public_enabled", "=", True)], limit=1)
        )
        if not document:
            return None
        return {"holder_name": document.holder_name, "title": document.title, "state": document.state}
