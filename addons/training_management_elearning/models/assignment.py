from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .version import COORDINATOR


def keep_criterion(records):
    if records:
        raise ValidationError('Keep the eLearning addon while interactive activities exist.')


class Assignment(models.Model):
    _name = 'training.elearning.assignment'
    _description = 'Interactive Programme Assignment'
    _check_company_auto = True
    name = fields.Char(required=True)
    program_id = fields.Many2one('training.program.version', required=True, ondelete='restrict', check_company=True)
    company_id = fields.Many2one(related='program_id.company_id', store=True)
    version_id = fields.Many2one('training.elearning.version', required=True, ondelete='restrict', check_company=True)
    objective = fields.Text(required=True)
    rule = fields.Selection([('completed', 'Completed'), ('score', 'Completed with score')], default='completed', required=True)
    threshold = fields.Float(default=70)
    counts_for_completion = fields.Boolean(string='Counts for the completion certificate', default=False,
        help='The result is declared by the browser. By default a human evidence decides the certificate.')
    state = fields.Selection([('draft','Draft'), ('validated','Validated')], default='draft', required=True, readonly=True)
    usage_ids = fields.One2many('training.elearning.usage', 'assignment_id', readonly=True)
    _threshold_valid = models.Constraint('CHECK(threshold >= 0 AND threshold <= 100)', 'Threshold must be between 0 and 100.')

    @api.model_create_multi
    def create(self, vals_list):
        vals_list=[self._add_missing_default_values(dict(values)) for values in vals_list]
        for values in vals_list:
            if values.get('state', 'draft') != 'draft' or values.get('usage_ids'):
                raise ValidationError(self.env._('Validate the draft through the publication action.'))
        return super().create(vals_list)

    def write(self, values):
        self.check_access('write')
        self.lock_for_update()
        self.invalidate_recordset()
        if 'state' in values or 'usage_ids' in values or any(a.state != 'draft' for a in self):
            raise ValidationError(self.env._('Preserve validated assignments; create a new assignment.'))
        return super().write(values)

    def action_validate(self):
        self.check_access('write')
        self.lock_for_update()
        self.invalidate_recordset()
        for assignment in self:
            if assignment.version_id.state != 'published' or not assignment.version_id.resource_id.active:
                raise ValidationError(self.env._('Select a published version of an active resource.'))
            if assignment.version_id.company_id != assignment.company_id:
                raise ValidationError(self.env._('Explicit cross-company sharing is not supported.'))
        return super().write({'state':'validated'})

    @api.private
    def _apply(self, deliveries):
        self.ensure_one()
        self.check_access('read')
        if not self.env.user.has_group(COORDINATOR):
            raise AccessError(self.env._('Coordination required.'))
        self.lock_for_update()
        self.invalidate_recordset()
        if self.state != 'validated' or self.version_id.state != 'published' or not self.version_id.resource_id.active:
            raise ValidationError(self.env._('Use a validated assignment with an available version.'))
        result=self.env['training.elearning.usage']
        with self.env.cr.savepoint():
            for delivery in deliveries:
                delivery.check_access('write')
                if delivery.program_id != self.program_id:
                    raise ValidationError(self.env._('The delivery must use the assigned programme.'))
                existing=result.search([('assignment_id','=',self.id),('delivery_id','=',delivery.id)])
                if existing:
                    result |= existing
                    continue
                activity=self.env['training.learning.activity'].create({'name':self.name,'delivery_id':delivery.id,'criterion':'elearning_formative'})
                result |= self.env['training.elearning.usage'].create({'assignment_id':self.id,'activity_id':activity.id})
        return result

    @api.ondelete(at_uninstall=False)
    def _keep_validated(self):
        if any(a.state == 'validated' for a in self):
            raise ValidationError(self.env._('Keep validated assignments.'))


class Usage(models.Model):
    _name = 'training.elearning.usage'
    _description = 'Interactive Delivery Usage'
    _check_company_auto = True
    _rec_name = 'activity_id'
    assignment_id = fields.Many2one('training.elearning.assignment', required=True, ondelete='restrict', check_company=True)
    activity_id = fields.Many2one('training.learning.activity', required=True, ondelete='restrict', check_company=True)
    delivery_id = fields.Many2one(related='activity_id.delivery_id', store=True)
    company_id = fields.Many2one(related='assignment_id.company_id', store=True)
    version_id = fields.Many2one(related='assignment_id.version_id', store=True)
    _one_activity = models.Constraint('UNIQUE(activity_id)', 'An activity has one interactive usage.')
    _one_assignment_delivery = models.Constraint('UNIQUE(assignment_id,delivery_id)', 'This assignment is already applied.')

    @api.constrains('assignment_id','activity_id')
    def _check_scope(self):
        for usage in self:
            if (usage.assignment_id.state != 'validated' or usage.version_id.state != 'published'
                    or not usage.version_id.resource_id.active
                    or usage.activity_id.criterion != 'elearning_formative'
                    or usage.activity_id.delivery_id.program_id != usage.assignment_id.program_id):
                raise ValidationError(self.env._('Select an available validated assignment and a compatible interactive activity.'))

    def write(self, values):
        raise ValidationError(self.env._('Keep historical content usages.'))

    @api.ondelete(at_uninstall=False)
    def _keep_usage(self):
        raise ValidationError(self.env._('Keep historical content usages.'))


class Activity(models.Model):
    _inherit = 'training.learning.activity'
    criterion = fields.Selection(selection_add=[('elearning_formative','Interactive formative activity')], ondelete={'elearning_formative':keep_criterion})
    elearning_usage_ids = fields.One2many('training.elearning.usage', 'activity_id', readonly=True)

    def write(self, values):
        if {'criterion','delivery_id','elearning_usage_ids'} & values.keys():
            if self.env['training.elearning.usage'].sudo().search_count([('activity_id','in',self.ids)]):
                raise ValidationError(self.env._('Preserve the activity and its content usage.'))
        return super().write(values)


class Progress(models.Model):
    _inherit = 'training.learning.progress'

    @api.private
    def _is_complete(self):
        self.ensure_one()
        if self.activity_id.criterion == 'elearning_formative':
            return False  # E04 introduces the authoritative formative evidence.
        return super()._is_complete()
