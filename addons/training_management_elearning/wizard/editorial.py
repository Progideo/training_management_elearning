from odoo import fields, models
from odoo.exceptions import ValidationError


class Import(models.TransientModel):
    _name = 'training.elearning.import'
    _description = 'Import Interactive Package'
    resource_id = fields.Many2one('training.elearning.resource', required=True)
    number = fields.Char(required=True)
    data = fields.Binary(required=True, attachment=False)
    filename = fields.Char()
    license_note = fields.Char(required=True)
    provenance = fields.Text(required=True)

    def action_import(self):
        self.ensure_one()
        self.check_access('read')
        version = self.env['training.elearning.version']._import(self.resource_id, self.number,
            self.data.content, self.license_note, self.provenance)
        return {'type':'ir.actions.act_window','res_model':version._name,'res_id':version.id,'view_mode':'form','target':'current'}


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


class Withdraw(models.TransientModel):
    _name = 'training.elearning.withdraw'
    _description = 'Withdraw Interactive Version'
    version_id = fields.Many2one('training.elearning.version', required=True)
    reason = fields.Text(required=True)

    def action_withdraw(self):
        self.ensure_one()
        self.check_access('read')
        self.version_id._withdraw(self.reason)
        return {'type':'ir.actions.act_window_close'}


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
