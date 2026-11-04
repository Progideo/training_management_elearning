"""Native tokens and attachment flags never publish curriculum or activation metadata files."""

from odoo import api, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from .course import AUTHOR, MANAGER

PATH_MODELS = {
    "training.elearning.path": AUTHOR,
    "training.elearning.path.line": AUTHOR,
    "training.elearning.path.registration": MANAGER,
    "training.elearning.path.activation": MANAGER,
    "training.elearning.path.item": MANAGER,
    "training.elearning.path.notice": MANAGER,
}


def target_of(record):
    target = record.sudo()
    if target._name == "ir.attachment" and target.res_model in PATH_MODELS:
        return record.env[target.res_model].sudo().browse(target.res_id).exists()
    return target if target._name in PATH_MODELS else None


def check_file(record):
    target = target_of(record)
    if target is None:
        return
    user = record.env.user
    if (
        not target
        or not user.active
        or not user.has_group(PATH_MODELS[target._name])
        or target.company_id not in user.company_ids
        or target.company_id not in record.env.companies
    ):
        raise AccessError(record.env._("This private curriculum file is unavailable."))


class Attachment(models.Model):
    _inherit = "ir.attachment"

    @api.private
    def _learning_path_mutation(self, values=None):
        values = values or {}
        targets = [(file.res_model, file.res_id) for file in self.sudo()]
        targets += [
            (values.get("res_model", file.res_model), values.get("res_id", file.res_id)) for file in self.sudo()
        ]
        if not self:
            targets.append((values.get("res_model"), values.get("res_id")))
        for model, record_id in targets:
            if model not in PATH_MODELS:
                continue
            target = self.env[model].browse(record_id).exists()
            if not target:
                raise AccessError(self.env._("This private curriculum context is unavailable."))
            check_file(target)
            path = (
                target
                if model == "training.elearning.path"
                else target.path_id
                if model == "training.elearning.path.line"
                else None
            )
            if path and path.bound_at:
                raise ValidationError(self.env._("Keep the files of registered curriculum editions."))
            if not path:
                raise AccessError(self.env._("Keep curriculum activation evidence in its checked native records."))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self.browse()._learning_path_mutation(
                {
                    "res_model": values.get("res_model", self.env.context.get("default_res_model")),
                    "res_id": values.get("res_id", self.env.context.get("default_res_id")),
                }
            )
        return super().create(vals_list)

    def write(self, values):
        if not (self.env.su and set(values) <= {"index_content"}):
            self._learning_path_mutation(values)
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _keep_path_files(self):
        self._learning_path_mutation()

    @api.model
    def _access_domain(self, operation):
        domain = super()._access_domain(operation)
        if operation == "read":
            for model, group in PATH_MODELS.items():
                companies = (
                    (self.env.companies & self.env.user.company_ids).ids
                    if self.env.user.active and self.env.user.has_group(group)
                    else []
                )
                blocked = self.env[model].sudo()._search(Domain("company_id", "not in", companies))
                domain &= ~(Domain("res_model", "=", model) & Domain("res_id", "any!", blocked))
        return domain

    def _to_http_stream(self):
        check_file(self)
        return super()._to_http_stream()


class Binary(models.AbstractModel):
    _inherit = "ir.binary"

    def _find_record(
        self,
        xmlid=None,
        res_model="ir.attachment",
        res_id=None,
        access_token=None,
        field=None,
    ):
        record = super()._find_record(xmlid, res_model, res_id, access_token, field)
        check_file(record)
        return record

    def _get_stream_from(self, record, *args, **kwargs):
        check_file(record)
        return super()._get_stream_from(record, *args, **kwargs)
