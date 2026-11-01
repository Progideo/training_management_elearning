import hashlib
import json
import math
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


def encode(value):
    try:
        result=json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError, RecursionError) as error:
        raise ValidationError('Invalid JSON report') from error
    if len(result.encode()) > 128 * 1024:
        raise ValidationError('Report exceeds 128 KiB')
    return result


class Attempt(models.Model):
    _name = 'training.elearning.attempt'
    _description = 'Interactive Formative Attempt'
    _check_company_auto = True
    _order = 'id desc'
    enrollment_id = fields.Many2one('training.enrollment',required=True,ondelete='restrict',check_company=True)
    usage_id = fields.Many2one('training.elearning.usage',required=True,ondelete='restrict',check_company=True)
    company_id = fields.Many2one(related='enrollment_id.company_id',store=True)
    version_id = fields.Many2one(related='usage_id.version_id',store=True)
    actor_id = fields.Many2one('res.users',required=True,ondelete='restrict')
    number = fields.Integer(required=True)
    request_key = fields.Char(required=True)
    revision = fields.Integer(default=0,readonly=True)
    state_json = fields.Text(default='{}',readonly=True,groups='base.group_system')
    result_json = fields.Text(default='{}',readonly=True,groups='base.group_system')
    score = fields.Float(readonly=True)
    maximum = fields.Float(readonly=True)
    completed = fields.Boolean(readonly=True)
    last_saved_at = fields.Datetime(readonly=True)
    event_ids = fields.One2many('training.elearning.event','attempt_id',readonly=True,groups='base.group_system')
    _one_number = models.Constraint('UNIQUE(enrollment_id,usage_id,number)','Unique attempt number required.')
    _one_request = models.Constraint('UNIQUE(request_key)','Unique launch request required.')

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError('Use the controlled launch service')

    def write(self, values):
        raise AccessError('Use the controlled report service')

    @api.ondelete(at_uninstall=False)
    def _keep_attempt(self):
        raise AccessError('Keep attempt history')

    @api.private
    def _scope(self, enrollment_id, usage_id, lock=False):
        service=self.env['training.learning.service']
        enrollment=service._enrollment(enrollment_id,lock=lock)
        usage=self.env['training.elearning.usage'].sudo().browse(usage_id).exists()
        if not usage or usage.delivery_id != enrollment.delivery_id or usage.company_id != enrollment.company_id:
            raise AccessError('Unavailable interactive activity')
        activity=service._activity(enrollment,usage.activity_id.id)
        if activity.criterion != 'elearning_formative' or usage.version_id.state != 'published':
            raise AccessError('Unavailable content version')
        return enrollment,usage,activity

    @api.private
    def _authorize(self, lock=False):
        self.ensure_one()
        attempt=self.sudo().exists()
        if not attempt or attempt.actor_id != self.env.user:
            raise AccessError('Unavailable attempt')
        enrollment,usage,activity=self._scope(attempt.enrollment_id.id,attempt.usage_id.id,lock=lock)
        return enrollment,usage,activity

    @api.private
    def _start(self, enrollment_id, usage_id, request_key, new=False):
        if not isinstance(request_key,str) or not 16 <= len(request_key) <= 80:
            raise ValidationError('Invalid launch request')
        with self.env.cr.savepoint():
            enrollment,usage,activity=self._scope(enrollment_id,usage_id,lock=True)
            existing=self.sudo().search([('request_key','=',request_key)],limit=1)
            if existing:
                if existing.enrollment_id != enrollment or existing.usage_id != usage or existing.actor_id != self.env.user:
                    raise ValidationError('Launch request conflict')
                return existing.with_user(self.env.user)
            latest=self.sudo().search([('enrollment_id','=',enrollment.id),('usage_id','=',usage.id)],order='number desc',limit=1)
            if latest and not new:
                return latest.with_user(self.env.user)
            attempt=super(Attempt,self.sudo().with_context({})).create({'enrollment_id':enrollment.id,'usage_id':usage.id,
                'actor_id':self.env.uid,'number':latest.number+1 if latest else 1,'request_key':request_key})
            return attempt.with_user(self.env.user)

    @api.private
    def _snapshot(self):
        self._authorize()
        attempt=self.sudo()
        return {'attempt':attempt.id,'number':attempt.number,'revision':attempt.revision,
                'state':json.loads(attempt.state_json),'result':json.loads(attempt.result_json)}

    @api.private
    def _save(self, key, revision, payload):
        # Must roll back even when a controller translates ValidationError to HTTP 409.
        with self.env.cr.savepoint():
            self._authorize(lock=True)
            attempt=self.sudo()
            attempt.lock_for_update()
            attempt.invalidate_recordset()
            if (not isinstance(key,str) or not 1 <= len(key) <= 80 or type(revision) is not int
                    or revision < 1 or not isinstance(payload,dict) or not payload
                    or set(payload)-{'state','result'}):
                raise ValidationError('Invalid event schema')
            encoded=encode({'revision':revision,'payload':payload})
            digest=hashlib.sha256(encoded.encode()).hexdigest()
            events=self.env['training.elearning.event'].sudo()
            previous=events.search([('attempt_id','=',attempt.id),('key','=',key)],limit=1)
            if previous:
                if previous.sha256 != digest:
                    raise ValidationError('Event key conflict')
                return json.loads(previous.receipt_json)
            latest=self.sudo().search([('enrollment_id','=',attempt.enrollment_id.id),('usage_id','=',attempt.usage_id.id)],order='number desc',limit=1)
            if latest != attempt or revision != attempt.revision+1:
                raise ValidationError('Stale attempt or revision; reload before continuing')
            values={'revision':revision,'last_saved_at':fields.Datetime.now()}
            if 'state' in payload:
                if not isinstance(payload['state'],dict):
                    raise ValidationError('Invalid resume state')
                values['state_json']=encode(payload['state'])
            if 'result' in payload:
                result=payload['result']
                if not isinstance(result,dict) or set(result) != {'score','maximum','completed'}:
                    raise ValidationError('Invalid result schema')
                score,maximum=result['score'],result['maximum']
                if (type(score) not in (int,float) or type(maximum) not in (int,float)
                        or not math.isfinite(score) or not math.isfinite(maximum)
                        or not 0 <= score <= maximum <= 100000 or type(result['completed']) is not bool):
                    raise ValidationError('Invalid formative result')
                if attempt.version_id.resource_id.format == 'h5p' and (score not in (0,1) or maximum != 1):
                    raise ValidationError('TrueFalse requires a whole-content result out of one')
                values.update(score=score,maximum=maximum,completed=result['completed'],result_json=encode(result))
            super(Attempt,attempt).write(values)
            receipt={'ok':True,'attempt':attempt.id,'revision':revision}
            event=events._append({'attempt_id':attempt.id,'key':key,'sha256':digest,
                'payload_json':encoded,'receipt_json':encode(receipt)})
            self._project(event)
            return receipt

    @api.private
    def _project(self, event):
        """E04 extends this transaction-local hook; no native result in E03."""
        return None


class Event(models.Model):
    _name = 'training.elearning.event'
    _description = 'Immutable Formative Event'
    attempt_id = fields.Many2one('training.elearning.attempt',required=True,ondelete='restrict')
    company_id = fields.Many2one(related='attempt_id.company_id',store=True)
    key = fields.Char(required=True)
    sha256 = fields.Char(required=True)
    payload_json = fields.Text(required=True,groups='base.group_system')
    receipt_json = fields.Text(required=True,groups='base.group_system')
    _one_event = models.Constraint('UNIQUE(attempt_id,key)','Unique event identity required.')

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError('Use the controlled report service')

    @api.private
    def _append(self, values):
        return super(Event,self.sudo().with_context({})).create(values)

    def write(self, values):
        raise AccessError('Events are immutable')

    @api.ondelete(at_uninstall=False)
    def _keep_event(self):
        raise AccessError('Keep original events')
