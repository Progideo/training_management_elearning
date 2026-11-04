"""Purchase summaries are scalar records; no native attachment or bearer file is supported."""

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain

REPORT = "training.elearning.sale.course.report"


class Attachment(models.Model):
    _inherit = "ir.attachment"

    @api.private
    def _check_report_target(self, values):
        if any(file.res_model == REPORT for file in self.sudo()) or values.get("res_model") == REPORT:
            raise AccessError(self.env._("Purchase summaries do not accept files or public attachments."))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self.browse()._check_report_target(
                {"res_model": values.get("res_model", self.env.context.get("default_res_model"))}
            )
        return super().create(vals_list)

    def write(self, values):
        self._check_report_target(values)
        return super().write(values)

    @api.model
    def _access_domain(self, operation):
        return super()._access_domain(operation) & Domain("res_model", "!=", REPORT)

    def _to_http_stream(self):
        self._check_report_target({})
        return super()._to_http_stream()


class Binary(models.AbstractModel):
    _inherit = "ir.binary"

    def _find_record(self, xmlid=None, res_model="ir.attachment", res_id=None, access_token=None, field=None):
        if res_model == REPORT:
            raise AccessError(self.env._("Purchase summaries are available only through their scoped portal."))
        record = super()._find_record(xmlid, res_model, res_id, access_token, field)
        if record._name == "ir.attachment":
            record._check_report_target({})
        return record
