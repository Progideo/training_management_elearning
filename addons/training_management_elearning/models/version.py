# SPDX-License-Identifier: LGPL-3.0-only
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.binary import BinaryBytes
from ..services.archive import parse_package

AUTHOR = 'training_management_elearning.group_elearning_author'
COORDINATOR = 'training_management.group_training_coordinator'
PROTECTED = ('training.elearning.file', 'training.elearning.version', 'training.elearning.import')


class Version(models.Model):
    _name = 'training.elearning.version'
    _description = 'Interactive Content Version'
    _check_company_auto = True
    _rec_name = 'number'
    resource_id = fields.Many2one('training.elearning.resource', required=True, ondelete='restrict', check_company=True)
    company_id = fields.Many2one(related='resource_id.company_id', store=True)
    number = fields.Char(required=True)
    sha256 = fields.Char(required=True, readonly=True)
    entrypoint = fields.Char(required=True, readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('published', 'Published'), ('withdrawn', 'Withdrawn')], default='draft', required=True, readonly=True)
    published_at = fields.Datetime(readonly=True)
    published_by_id = fields.Many2one('res.users', readonly=True, ondelete='restrict')
    withdrawal_reason = fields.Text(readonly=True)
    license_note = fields.Char(required=True, readonly=True)
    provenance = fields.Text(required=True, readonly=True)
    file_ids = fields.One2many('training.elearning.file', 'version_id', groups='base.group_system')
    _number_unique = models.Constraint('UNIQUE(resource_id,number)', 'This version already exists.')

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._('Use the controlled package import.'))

    @api.private
    def _import(self, resource, number, raw, license_note, provenance):
        resource.ensure_one()
        resource.check_access('write')
        if not self.env.user.active or not (self.env.user.has_group(AUTHOR) or self.env.user.has_group(COORDINATOR)):
            raise AccessError(self.env._('Content author permission required.'))
        if not resource.active or not number.strip() or not license_note.strip() or not provenance.strip():
            raise ValidationError(self.env._('Specify version, license and provenance for an active resource.'))
        try:
            result = parse_package(raw, resource.format)
        except ValueError as error:
            raise ValidationError(str(error)) from error
        with self.env.cr.savepoint():
            version = super(Version, self).create({'resource_id': resource.id, 'number': number,
                'sha256': result['sha256'], 'entrypoint': result['entrypoint'],
                'license_note': license_note, 'provenance': provenance})
            self.env['training.elearning.file']._insert([
                {'version_id': version.id, 'path': path, 'data': BinaryBytes(data)}
                for path, data in result['files'].items()])
            return version

    def write(self, values):
        raise ValidationError(self.env._('Import a new version; preserve existing content.'))

    @api.ondelete(at_uninstall=False)
    def _keep_history(self):
        raise ValidationError(self.env._('Keep content versions and their history.'))

    def action_publish(self):
        self.check_access('write')
        if not self.env.user.has_group(COORDINATOR):
            raise AccessError(self.env._('Only coordination may publish content.'))
        self.lock_for_update()
        self.invalidate_recordset()
        if any(v.state != 'draft' or not v.resource_id.active for v in self):
            raise ValidationError(self.env._('Publish a draft of an active resource.'))
        return super().write({'state': 'published', 'published_at': fields.Datetime.now(), 'published_by_id': self.env.uid})

    @api.private
    def _withdraw(self, reason):
        self.check_access('write')
        if not self.env.user.has_group(COORDINATOR) or not reason.strip():
            raise AccessError(self.env._('Coordination and a reason are required.'))
        self.lock_for_update()
        return super().write({'state': 'withdrawn', 'withdrawal_reason': reason})

    def action_preview(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_url', 'url': '/training/interactive/preview/%s' % self.id, 'target': 'new'}


class PackageFile(models.Model):
    _name = 'training.elearning.file'
    _description = 'Private Interactive Content File'
    version_id = fields.Many2one('training.elearning.version', required=True, ondelete='restrict')
    path = fields.Char(required=True)
    data = fields.Binary(required=True, attachment=False, groups='base.group_system')
    _path_unique = models.Constraint('UNIQUE(version_id,path)', 'Unique package path required.')

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._('Use the controlled package import.'))

    @api.private
    def _insert(self, values):
        return super(PackageFile, self.sudo()).create(values)

    def write(self, values):
        raise AccessError(self.env._('Package files are immutable.'))

    @api.ondelete(at_uninstall=False)
    def _keep_files(self):
        raise AccessError(self.env._('Keep historical package files.'))


class Binary(models.AbstractModel):
    _inherit = 'ir.binary'

    def _record_to_stream(self, record, field_name):
        if record._name in PROTECTED or (record._name == 'ir.attachment' and record.sudo().res_model in PROTECTED):
            raise AccessError(self.env._('Interactive packages require the isolated content origin.'))
        return super()._record_to_stream(record, field_name)


class Attachment(models.Model):
    _inherit = 'ir.attachment'

    def _to_http_stream(self):
        if any(a.sudo().res_model in PROTECTED for a in self):
            raise AccessError(self.env._('Interactive packages require the isolated content origin.'))
        return super()._to_http_stream()
