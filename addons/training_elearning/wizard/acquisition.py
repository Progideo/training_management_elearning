"""An explicit staff decision, scoped before creating a temporary form."""

from uuid import uuid4
from odoo import api, fields, models
from odoo.exceptions import AccessError
from ..models.acquisition import coordinator


class Invalidate(models.TransientModel):
    _name = "training.elearning.acquisition.invalidate"
    _description = "Motivated Acquisition Decision"
    membership_id = fields.Many2one("slide.channel.partner", required=True, readonly=True)
    company_id = fields.Many2one(related="membership_id.channel_id.learning_company_id")
    slide_id = fields.Many2one("slide.slide", required=True)
    allowed_slide_ids = fields.Many2many("slide.slide", compute="_compute_slides")
    reason = fields.Text(required=True)
    withdraw_certificates = fields.Boolean(
        string="Retirer les attestations dont les obligations deviennent incomplètes"
    )
    request_key = fields.Char(default=lambda self: str(uuid4()), required=True, copy=False)

    @api.depends("membership_id")
    def _compute_slides(self):
        for wizard in self:
            if wizard.membership_id:
                coordinator(wizard.membership_id)
                plan = wizard.membership_id._learning_plan()["slides"]
                rows = (
                    self.env["slide.slide.partner"]
                    .sudo()
                    .search(
                        [
                            ("slide_id", "in", [item["id"] for item in plan]),
                            ("partner_id", "=", wizard.membership_id.partner_id.id),
                            ("completed", "=", True),
                        ]
                    )
                )
                wizard.allowed_slide_ids = rows.slide_id
            else:
                wizard.allowed_slide_ids = False

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            member = self.env["slide.channel.partner"].browse(
                values.get("membership_id") or self.env.context.get("default_membership_id")
            )
            coordinator(member)
            if values.get("slide_id") and values["slide_id"] not in [
                item["id"] for item in member._learning_plan()["slides"]
            ]:
                raise AccessError(self.env._("Use an activity from this learner context."))
        return super().create(vals_list)

    def write(self, values):
        for wizard in self:
            member = self.env["slide.channel.partner"].browse(values.get("membership_id") or wizard.membership_id.id)
            coordinator(member)
            if values.get("slide_id") and values["slide_id"] not in [
                item["id"] for item in member._learning_plan()["slides"]
            ]:
                raise AccessError(self.env._("Use an activity from this learner context."))
        return super().write(values)

    def action_apply(self):
        self.ensure_one()
        event = self.env["training.elearning.acquisition.invalidation"]._invalidate(
            self.membership_id,
            self.slide_id.id,
            self.reason,
            self.request_key,
            withdraw_certificates=self.withdraw_certificates,
        )
        return {"type": "ir.actions.act_window", "res_model": event._name, "res_id": event.id, "view_mode": "form"}
