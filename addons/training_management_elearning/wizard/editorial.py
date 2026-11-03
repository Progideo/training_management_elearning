from odoo import fields, models
from odoo.exceptions import ValidationError


class Apply(models.TransientModel):
    _name = 'training.elearning.apply'
    _description = 'Apply Interactive Assignment'
    assignment_id = fields.Many2one('training.elearning.assignment', required=True)
    delivery_ids = fields.Many2many('training.delivery', required=True)

    def action_apply(self):
        self.ensure_one()
        self.check_access('read')
        if not self.delivery_ids:
            raise ValidationError(self.env._('Select at least one delivery.'))
        usages=self.assignment_id._apply(self.delivery_ids)
        return {'type':'ir.actions.act_window','res_model':usages._name,'view_mode':'list,form','domain':[('id','in',usages.ids)]}


class Invalidate(models.TransientModel):
    _name = 'training.elearning.invalidate'
    _description = 'Invalidate Formative Acquisition'
    progress_id = fields.Many2one('training.learning.progress',required=True)
    reason = fields.Text(required=True)

    def action_invalidate(self):
        self.ensure_one()
        self.check_access('read')
        self.progress_id._invalidate_formative(self.reason)
        return {'type':'ir.actions.act_window_close'}
