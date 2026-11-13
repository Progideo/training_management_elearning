"""Native explicit manual curriculum authorization and motivated start-window adjustments."""

from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, ValidationError


class Activate(models.TransientModel):
    _name = "training.elearning.path.activate"
    _description = "Authorize Native Curriculum Courses"
    path_id = fields.Many2one("training.elearning.path", required=True)
    partner_id = fields.Many2one("res.partner", required=True)
    course_ids = fields.Many2many("slide.channel", required=True)
    access_months = fields.Integer(default=6, required=True)
    start_months = fields.Integer(default=12, required=True)
    reason = fields.Text(required=True)
    activation_id = fields.Many2one("training.elearning.path.activation", readonly=True, ondelete="restrict")

    @api.model_create_multi
    def create(self, vals_list):
        if any("activation_id" in values for values in vals_list) or "default_activation_id" in self.env.context:
            raise AccessError(self.env._("The server records this curriculum authorization result."))
        return super().create(vals_list)

    def write(self, values):
        if "activation_id" in values or self.filtered("activation_id"):
            raise AccessError(self.env._("Prepare a new authorization instead of changing an applied curriculum form."))
        return super().write(values)

    @api.onchange("path_id")
    def _onchange_path(self):
        self.course_ids = self.path_id.line_ids.course_id

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        path = self.env["training.elearning.path"].browse(
            values.get("path_id") or self.env.context.get("default_path_id")
        )
        if path and "course_ids" in field_names:
            path._staff(manager=True)
            values["course_ids"] = [Command.set(path.line_ids.course_id.ids)]
        return values

    def action_activate(self):
        self.ensure_one()
        self.path_id._staff(manager=True)
        self.lock_for_update()
        self.invalidate_recordset()
        if self.activation_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "training.elearning.path.activation",
                "res_id": self.activation_id.id,
                "view_mode": "form",
            }
        if not self.course_ids:
            raise ValidationError(self.env._("Select the explicitly authorized curriculum courses."))
        plan = self.path_id._plan(self.course_ids.ids)
        activation = self.env["training.elearning.path.activation"]._activate(
            self.path_id,
            self.partner_id,
            plan,
            self.access_months,
            self.start_months,
            self.reason,
        )
        super(Activate, self).write({"activation_id": activation.id})  # pylint: disable=super-method-mismatch
        return {
            "type": "ir.actions.act_window",
            "res_model": activation._name,
            "res_id": activation.id,
            "view_mode": "form",
        }


class Adjust(models.TransientModel):
    _name = "training.elearning.path.adjust"
    _description = "Motivated Curriculum Start Window Adjustment"
    activation_id = fields.Many2one("training.elearning.path.activation", required=True, readonly=True)
    starts_until = fields.Datetime(required=True)
    paused = fields.Boolean(string="Pause Future Course Starts")
    reason = fields.Text(required=True)

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        activation = self.env["training.elearning.path.activation"].browse(
            values.get("activation_id") or self.env.context.get("default_activation_id")
        )
        if activation:
            activation._staff()
            if "starts_until" in field_names:
                values["starts_until"] = activation.starts_until
            if "paused" in field_names:
                values["paused"] = activation.start_paused
        return values

    def action_apply(self):
        self.ensure_one()
        self.activation_id._adjust(self.starts_until, self.reason, paused=self.paused)
        return {"type": "ir.actions.act_window_close"}
