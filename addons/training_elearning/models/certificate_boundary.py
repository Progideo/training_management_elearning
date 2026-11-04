"""Issued PDFs never inherit native public attachment or bearer-token access."""

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain

MODELS = (
    "training.elearning.certificate",
    "training.elearning.certificate.consent",
    "training.elearning.certificate.notice",
    "training.elearning.acquisition.invalidation",
    "training.elearning.acquisition.invalidate",
)


class Attachment(models.Model):
    _inherit = "ir.attachment"

    @api.private
    def _check_certificate_target(self, values):
        if any(file.res_model in MODELS for file in self.sudo()) or values.get("res_model") in MODELS:
            raise AccessError(self.env._("Certificate records use their immutable PDF and checked private download."))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self.browse()._check_certificate_target(
                {"res_model": values.get("res_model", self.env.context.get("default_res_model"))}
            )
        return super().create(vals_list)

    def write(self, values):
        self._check_certificate_target(values)
        return super().write(values)

    @api.model
    def _access_domain(self, operation):
        return super()._access_domain(operation) & Domain("res_model", "not in", MODELS)

    def _to_http_stream(self):
        self._check_certificate_target({})
        return super()._to_http_stream()


class Binary(models.AbstractModel):
    _inherit = "ir.binary"

    def _find_record(self, xmlid=None, res_model="ir.attachment", res_id=None, access_token=None, field=None):
        if res_model in MODELS:
            raise AccessError(self.env._("Use the authorized private certificate download."))
        record = super()._find_record(xmlid, res_model, res_id, access_token, field)
        if record._name in MODELS:
            raise AccessError(self.env._("Use the authorized private certificate download."))
        if record._name == "ir.attachment":
            record._check_certificate_target({})
        return record

    def _get_stream_from(self, record, *args, **kwargs):
        if record._name in MODELS:
            raise AccessError(self.env._("Use the authorized private certificate download."))
        if record._name == "ir.attachment":
            record._check_certificate_target({})
        return super()._get_stream_from(record, *args, **kwargs)
