from odoo import fields, models


class Availability(models.TransientModel):
    _name = "training.elearning.availability"
    _description = "Motivated Learning Activity Availability"
    slide_id = fields.Many2one("slide.slide", required=True)
    reopen = fields.Boolean(string="Reopen This Activity")
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        self.slide_id.action_learning_change_availability(self.reason, self.reopen)
        return {"type": "ir.actions.act_window_close"}
