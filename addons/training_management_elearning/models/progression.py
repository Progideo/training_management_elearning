import json
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .version import COORDINATOR


class Progress(models.Model):
    _inherit = 'training.learning.progress'
    elearning_completed = fields.Boolean(readonly=True,copy=False)
    elearning_event_id = fields.Many2one('training.elearning.event',readonly=True,copy=False,ondelete='restrict',groups='base.group_system')
    elearning_invalidated_attempt_number = fields.Integer(readonly=True,copy=False,groups='base.group_system')

    @api.depends('elearning_completed')
    def _compute_completed(self):
        return super()._compute_completed()

    @api.private
    def _is_complete(self):
        self.ensure_one()
        if self.activity_id.criterion == 'elearning_formative':
            return self.elearning_completed
        return super()._is_complete()

    @api.private
    def _refresh_paths(self):
        enrollment=self.sudo().enrollment_id
        refs=self.env['training.path.assignment'].sudo().search([('enrollment_id','=',enrollment.id),('withdrawn_at','=',False)])
        affected=self.env['training.path.assignment'].sudo().search([('path_id','in',refs.path_id.ids),
            ('participant_id','=',enrollment.participant_id.id),('withdrawn_at','=',False)])
        affected.invalidate_recordset(['completed','blocked'])
        affected.enrollment_id.invalidate_recordset(['effective_access'])

    @api.private
    def _invalidate_formative(self, reason):
        self.ensure_one()
        self.check_access('read')
        if not self.env.user.has_group(COORDINATOR) or not reason.strip():
            raise AccessError('Coordination and a reason are required')
        progress=self.sudo()
        enrollment=progress.enrollment_id.with_user(self.env.user)
        enrollment._require_coordinator()
        enrollment.delivery_id._serialize()
        enrollment.lock_for_update()
        progress.invalidate_recordset()
        if not progress.elearning_completed or progress.activity_id.criterion!='elearning_formative':
            raise ValidationError('No formative acquisition to invalidate')
        latest=self.env['training.elearning.attempt'].sudo().search([('enrollment_id','=',enrollment.id),
            ('usage_id.activity_id','=',progress.activity_id.id)],order='number desc',limit=1)
        self.env['training.elearning.invalidation']._append({'progress_id':progress.id,'event_id':progress.elearning_event_id.id,
            'actor_id':self.env.uid,'reason':reason,'through_attempt_number':latest.number})
        progress._store_evidence({'elearning_completed':False,'elearning_event_id':False,
            'elearning_invalidated_attempt_number':latest.number,'revision':progress.revision+1})
        progress._refresh_paths()
        return True


class Attempt(models.Model):
    _inherit = 'training.elearning.attempt'

    @api.private
    def _project(self,event):
        result=json.loads(event.sudo().payload_json)['payload'].get('result')
        if not result or not result['completed']:
            return None
        enrollment,usage,activity=self._authorize()
        policy=usage.assignment_id
        if policy.rule=='score' and (result['maximum']<=0 or 100*result['score']/result['maximum']<policy.threshold):
            return None
        progress=self.env['training.learning.service']._progress(enrollment,activity,create=True)
        if progress.elearning_completed or self.sudo().number<=progress.elearning_invalidated_attempt_number:
            return None
        progress._store_evidence({'elearning_completed':True,'elearning_event_id':event.id,'revision':progress.revision+1})
        progress._refresh_paths()
        return None


class Path(models.Model):
    _inherit = 'training.path.assignment'

    @api.depends('enrollment_id.learning_progress_ids.elearning_completed')
    def _compute_status(self):
        return super()._compute_status()


class Service(models.AbstractModel):
    _inherit = 'training.learning.service'

    @api.private
    def _required_for_certificate(self,activity):
        if activity.criterion!='elearning_formative':
            return super()._required_for_certificate(activity)
        usage=self.env['training.elearning.usage'].sudo().search([('activity_id','=',activity.id)],limit=1)
        return usage.assignment_id.counts_for_completion

    @api.private
    def _certificate_origin(self,enrollment,activity):
        origin=super()._certificate_origin(enrollment,activity)
        if activity.criterion=='elearning_formative':
            progress=self._progress(enrollment,activity)
            event=progress.elearning_event_id
            origin['formative']={'event':event.id,'event_sha256':event.sha256,'attempt':event.attempt_id.id,
                'content_version':event.attempt_id.version_id.id,'content_sha256':event.attempt_id.version_id.sha256,
                'nature':'untrusted_client_formative'}
        return origin


class Invalidation(models.Model):
    _name = 'training.elearning.invalidation'
    _description = 'Formative Acquisition Invalidation'
    progress_id = fields.Many2one('training.learning.progress',required=True,ondelete='restrict')
    company_id = fields.Many2one(related='progress_id.company_id',store=True)
    event_id = fields.Many2one('training.elearning.event',required=True,ondelete='restrict')
    actor_id = fields.Many2one('res.users',required=True,ondelete='restrict')
    reason = fields.Text(required=True)
    through_attempt_number = fields.Integer(required=True)

    @api.model_create_multi
    def create(self,vals_list):
        raise AccessError('Use the controlled invalidation action')

    @api.private
    def _append(self,values):
        return super(Invalidation,self.sudo().with_context({})).create(values)

    def write(self,values):
        raise AccessError('Keep the original invalidation decision')

    @api.ondelete(at_uninstall=False)
    def _keep_audit(self):
        raise AccessError('Keep invalidation history')
