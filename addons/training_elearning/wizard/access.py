from odoo import fields, models


class Access(models.TransientModel):
    _name = "training.elearning.access"
    _description = "Controlled eLearning Access"
    membership_id = fields.Many2one("slide.channel.partner", required=True)
    operation = fields.Selection(
        [("activate", "Activate or Renew"), ("suspend", "Suspend"), ("revoke", "Revoke")],
        required=True,
        default="activate",
    )
    user_id = fields.Many2one("res.users")
    ends_at = fields.Datetime()
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        if self.operation == "activate":
            self.membership_id.action_learning_activate(self.ends_at, self.user_id.id, self.reason)
        elif self.operation == "suspend":
            self.membership_id.action_learning_suspend(self.reason)
        else:
            self.membership_id.action_learning_revoke(self.reason)
        return {"type": "ir.actions.act_window_close"}
