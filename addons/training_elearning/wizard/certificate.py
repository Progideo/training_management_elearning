"""Motivated certificate withdrawal, replacement and public deactivation."""

from odoo import fields, models
from odoo.exceptions import ValidationError
from ..models.certificate import staff


class Change(models.TransientModel):
    _name = "training.elearning.certificate.change"
    _description = "Change Learning Certificate Status"
    certificate_id = fields.Many2one("training.elearning.certificate", required=True, readonly=True)
    operation = fields.Selection(
        [("withdrawn", "Retirer l’attestation"), ("disable", "Désactiver la vérification publique")],
        required=True,
        default="withdrawn",
    )
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        staff(self.certificate_id)
        if not (self.reason or "").strip():
            raise ValidationError(self.env._("Provide an internal reason."))
        if self.operation == "withdrawn":
            self.certificate_id._change("withdrawn", self.reason)
        else:
            self.certificate_id._disable_public(self.reason)
        return {"type": "ir.actions.act_window_close"}


class Replace(models.TransientModel):
    _name = "training.elearning.certificate.replace"
    _description = "Replace Learning Certificate"
    consent_id = fields.Many2one("training.elearning.certificate.consent", required=True, readonly=True)
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        staff(self.consent_id)
        if not (self.reason or "").strip():
            raise ValidationError(self.env._("Explain this replacement."))
        document = self.consent_id._issue(replacement_reason=self.reason)
        return {
            "type": "ir.actions.act_window",
            "res_model": document._name,
            "res_id": document.id,
            "view_mode": "form",
        }
