# SPDX-License-Identifier: LGPL-3.0-only
import uuid
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class Resource(models.Model):
    """Editorial identity only. E00 cannot upload, publish or execute packages."""
    _name = "training.elearning.resource"
    _description = "Interactive Learning Resource"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    identifier = fields.Char(required=True, default=lambda self: str(uuid.uuid4()), copy=False, readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    version_ids = fields.One2many('training.elearning.version', 'resource_id', readonly=True)
    active = fields.Boolean(default=True)
    format = fields.Selection([("h5p", "H5P"), ("scorm12", "SCORM 1.2")], required=True)
    provenance = fields.Text()
    license_note = fields.Char(string="Content license")

    _identifier_unique = models.Constraint("UNIQUE(identifier)", "The resource identifier must be unique.")

    def write(self, vals):
        if {"identifier", "company_id", "format"} & vals.keys():
            raise ValidationError(_("Keep the resource identity, owner and format; create another resource instead."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _keep_identity(self):
        raise ValidationError(_("Archive resources to preserve their identity."))
