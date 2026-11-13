"""Autonomous lesson capabilities extend the same common reader and version bytes."""

from odoo import api, fields, models
from odoo.exceptions import AccessError


class Lease(models.Model):
    _inherit = "training.elearning.lease"
    learning_attempt_id = fields.Many2one("training.elearning.interactive.attempt", ondelete="restrict")

    @api.private
    def _context_values(self, version, attempt):
        if not attempt or getattr(attempt, "_name", None) != "training.elearning.interactive.attempt":
            return super()._context_values(version, attempt)
        attempt.with_env(self.env)._authorize()
        if attempt.sudo().version_id != version:
            raise AccessError(self.env._("This reader must use the frozen autonomous attempt version."))
        return {"learning_attempt_id": attempt.id}

    @api.private
    def _check_context(self):
        lease = self.sudo()
        if not lease.learning_attempt_id:
            return super()._check_context()
        lease.learning_attempt_id.with_user(lease.user_id)._authorize()
        return None

    @api.private
    def _is_preview(self):
        return False if self.sudo().learning_attempt_id else super()._is_preview()

    @api.private
    def _content_snapshot(self):
        lease = self.sudo()
        if not lease.learning_attempt_id:
            return super()._content_snapshot()
        return lease.learning_attempt_id.with_user(lease.user_id)._snapshot()

    @api.private
    def _player_context(self):
        values = super()._player_context()
        attempt = self.sudo().learning_attempt_id
        if attempt:
            values.update(
                attempt=attempt.id,
                revision=attempt.revision,
                save="/my/learning-interactive/attempt/%s/save" % attempt.id,
                renew="/my/learning-interactive/attempt/%s/renew" % attempt.id,
                back="/my/learning/%s" % attempt.membership_id.id,
            )
        return values
