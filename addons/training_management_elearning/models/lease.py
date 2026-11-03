"""Bind common reader capabilities to the existing TM enrollment and attempt."""

from odoo import api, fields, models
from odoo.exceptions import AccessError


class Lease(models.Model):
    _inherit = "training.elearning.lease"

    attempt_id = fields.Many2one("training.elearning.attempt", ondelete="restrict")

    @api.private
    def _context_values(self, version, attempt):
        if not attempt:
            return super()._context_values(version, attempt)
        if getattr(attempt, "_name", None) != "training.elearning.attempt":
            raise AccessError(self.env._("Unsupported learner context."))
        attempt.with_env(self.env)._authorize()
        if attempt.sudo().version_id != version:
            raise AccessError(self.env._("Attempt version mismatch."))
        return {"attempt_id": attempt.id}

    @api.private
    def _check_context(self):
        lease = self.sudo()
        if not lease.attempt_id:
            return super()._check_context()
        lease.attempt_id.with_user(lease.user_id)._authorize()
        return None

    @api.private
    def _is_preview(self):
        return not self.sudo().attempt_id

    @api.private
    def _content_snapshot(self):
        lease = self.sudo()
        if not lease.attempt_id:
            return super()._content_snapshot()
        return lease.attempt_id.with_user(lease.user_id)._snapshot()

    @api.private
    def _player_context(self):
        values = super()._player_context()
        attempt = self.sudo().attempt_id
        if attempt:
            values.update(
                attempt=attempt.id,
                revision=attempt.revision,
                save="/training/interactive/attempt/%s/save" % attempt.id,
                renew="/training/interactive/attempt/%s/renew" % attempt.id,
                back="/my/trainings/%s" % attempt.enrollment_id.id,
            )
        return values
