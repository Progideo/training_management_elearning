import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .version import AUTHOR, COORDINATOR


class Lease(models.Model):
    _name = 'training.elearning.lease'
    _description = 'Short-lived Content Authorization'
    version_id = fields.Many2one('training.elearning.version', required=True, ondelete='restrict')
    user_id = fields.Many2one('res.users', required=True, ondelete='restrict')
    token_hash = fields.Char(required=True, index=True)
    nonce = fields.Char(required=True)
    expires_at = fields.Datetime(required=True)
    attempt_id = fields.Many2one('training.elearning.attempt', ondelete='restrict')
    _token_unique = models.Constraint('UNIQUE(token_hash)', 'Unique content authorization required.')

    @api.private
    def _origins(self):
        params = self.env['ir.config_parameter'].sudo()
        origins = [params.get_str('training_elearning.' + name, '') for name in ('portal_origin', 'content_origin')]
        parsed = [urlsplit(value) for value in origins]
        for value, url in zip(origins, parsed):
            if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
                    or url.query or url.fragment or url.path or value != url.scheme + '://' + url.netloc
                    or (url.scheme != 'https' and url.hostname not in ('localhost', '127.0.0.1'))):
                raise ValidationError(self.env._('Configure secure portal and isolated content origins.'))
        if parsed[0].hostname == parsed[1].hostname:
            raise ValidationError(self.env._('The content origin must use a separate hostname.'))
        return origins

    @api.private
    def _preview_access(self, version):
        if (not self.env.user.active or self.env.user._is_public()
                or not (self.env.user.has_group(AUTHOR) or self.env.user.has_group(COORDINATOR))):
            raise AccessError(self.env._('Content author permission required.'))
        version.check_access('read')
        if version.state == 'withdrawn':
            raise AccessError(self.env._('Content withdrawn.'))

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._('Use the controlled launch service.'))

    @api.private
    def _issue(self, version, attempt=None):
        self._origins()
        if attempt:
            attempt._authorize()
            if attempt.sudo().version_id != version:
                raise AccessError('Attempt version mismatch')
        else:
            self._preview_access(version)
        token = secrets.token_urlsafe(32)
        lease = super(Lease, self.sudo().with_context({})).create({'version_id': version.id, 'user_id': self.env.uid,
            'attempt_id': attempt.id if attempt else False, 'token_hash': hashlib.sha256(token.encode()).hexdigest(),
            'nonce': secrets.token_urlsafe(24), 'expires_at': fields.Datetime.now() + timedelta(minutes=5)})
        return lease, token

    @api.private
    def _resolve(self, token):
        if not isinstance(token, str) or len(token) != 43:
            raise AccessError('Unavailable content')
        lease = self.sudo().search([('token_hash', '=', hashlib.sha256(token.encode()).hexdigest())], limit=1)
        if not lease or lease.expires_at <= fields.Datetime.now() or not lease.user_id.active:
            raise AccessError('Expired content authorization')
        if lease.version_id.state == 'withdrawn':
            raise AccessError('Withdrawn content')
        actor = self.with_user(lease.user_id)
        if lease.attempt_id:
            lease.attempt_id.with_user(lease.user_id)._authorize()
        else:
            actor._preview_access(lease.version_id.with_user(lease.user_id))
        return lease

    @api.private
    def _renew(self):
        self.ensure_one()
        if self.attempt_id:
            self.attempt_id.with_user(self.user_id)._authorize()
        else:
            self.with_user(self.user_id)._preview_access(self.version_id.with_user(self.user_id))
        self.lock_for_update()
        return super().write({'expires_at':fields.Datetime.now()+timedelta(minutes=5)})

    @api.autovacuum
    def _gc_expired(self):
        # Leases are transient read capabilities, never the retained learning evidence.
        self.sudo().search([('expires_at', '<', fields.Datetime.now()-timedelta(days=1))]).unlink()

    def write(self, vals):
        raise AccessError('Immutable launch authorization')
