from odoo import fields, models


class Authorization(models.TransientModel):
    _name = "training.elearning.sale.authorization"
    _description = "Authorize Autonomous Sale Access"
    line_id = fields.Many2one("sale.order.line", required=True)
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        self.line_id.action_learning_authorize(self.reason)
        return {"type": "ir.actions.act_window_close"}
