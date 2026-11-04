"""Reuse the native account service before an explicitly authorized commercial grant."""

from odoo import api, fields, models
from .offer import require_manager


class Allocation(models.Model):
    _inherit = "training.elearning.sale.allocation"

    def action_learning_activate(self):
        self.ensure_one()
        with self.env.cr.savepoint():
            require_manager(self)
            self.line_id.lock_for_update()
            self.lock_for_update()
            self.invalidate_recordset()
            line = self.line_id
            line.invalidate_recordset()
            accounts = self.env["training.elearning.account.service"]
            mails = self.env["mail.mail"].browse()
            user = self.env["res.users"].browse()
            if (
                not self.activated_at
                and line.state == "sale"
                and line.learning_authorized_at
                and line.learning_assign_until
                and fields.Datetime.now() < line.learning_assign_until
            ):
                user, mails = accounts._prepare(self.partner_id, self.company_id)
            result = super().action_learning_activate()
            accounts._bind(self, user, mails)
            return result


class Reminder(models.Model):
    _inherit = "training.elearning.reminder"
    allocation_id = fields.Many2one("training.elearning.sale.allocation", readonly=True, ondelete="restrict")

    @api.private
    def _source_field(self, source):
        return (
            "allocation_id" if source._name == "training.elearning.sale.allocation" else super()._source_field(source)
        )

    @api.private
    def _target(self):
        if self.kind != "invitation" or not self.allocation_id:
            return super()._target()
        seat = self.sudo().allocation_id
        line = seat.line_id
        users = seat.partner_id.with_context(active_test=False).user_ids
        if len(users) != 1 or not users.active or users._is_public() or users.partner_id != seat.partner_id:
            return False
        if not seat.activated_at or not line.learning_authorized_at:
            return False
        if seat.membership_id:
            member = seat.membership_id
            if (
                member.learning_user_id != users
                or not member.active
                or member.learning_state != "active"
                or member.learning_ends_at <= fields.Datetime.now()
            ):
                return False
        elif not seat.path_activation_id or not seat.path_activation_id._authorized():
            return False
        return {"user": users, "company": seat.company_id, "deadline": False, "url": "/web/login"}
