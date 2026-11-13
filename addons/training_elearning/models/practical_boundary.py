# pylint: disable=super-method-mismatch  # checked private transitions bypass public mutation guards
"""Neither native tokens nor public flags reveal task definitions or private rendus."""

from odoo import api, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from .practical import AUTHOR
from .submission import PEDAGOGY

TASK = "training.elearning.practical"
PAYLOAD = "training.elearning.submission.payload"


def target_of(record):
    target = record.sudo()
    if target._name == "ir.attachment" and target.res_model in (TASK, PAYLOAD):
        return record.env[target.res_model].sudo().browse(target.res_id).exists()
    return target if target._name in (TASK, PAYLOAD) else None


def check_file(record):
    target = target_of(record)
    if target is None:
        return
    if not target:
        raise AccessError(record.env._("This private practical file is unavailable."))
    if target._name == PAYLOAD:
        target.with_env(record.env)._authorize_staff()
    else:
        user = record.env.user
        if (
            not user.active
            or not user.has_group(AUTHOR)
            or target.company_id not in user.company_ids
            or target.company_id not in record.env.companies
        ):
            raise AccessError(record.env._("This private practical definition file is unavailable."))


class Attachment(models.Model):
    _inherit = "ir.attachment"  # pylint: disable=consider-merging-classes-inherited

    @api.private
    def _learning_task_mutation(self, values=None):
        values = values or {}
        targets = []
        for file in self.sudo():
            targets.append((file.res_model, file.res_id))
            targets.append((values.get("res_model", file.res_model), values.get("res_id", file.res_id)))
        if not self:
            targets.append((values.get("res_model"), values.get("res_id")))
        for model, record_id in targets:
            if model == PAYLOAD:
                raise AccessError(self.env._("Use the checked private submission upload; its files remain immutable."))
            if model == TASK:
                task = self.env[TASK].browse(record_id).exists()
                if task:
                    task._staff()
                    if task.state == "published":
                        raise ValidationError(self.env._("Keep the files of published practical versions."))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self.browse()._learning_task_mutation(
                {
                    "res_model": values.get("res_model", self.env.context.get("default_res_model")),
                    "res_id": values.get("res_id", self.env.context.get("default_res_id")),
                }
            )
        return super().create(vals_list)

    def write(self, values):
        # Indexing is derived native metadata; it cannot change the retained bytes.
        if not (self.env.su and set(values) <= {"index_content"}):
            self._learning_task_mutation(values)
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _keep_practical_files(self):
        self._learning_task_mutation()

    @api.private
    def _learning_submission_file(self, payload, item):  # pylint: disable=super-method-mismatch,context-overridden
        member = payload.sudo().submission_id.membership_id
        user = self.env.user
        if (
            member.learning_user_id != user
            or member.partner_id != user.partner_id
            or not user.active
            or member.channel_id.learning_company_id not in user.company_ids
        ):
            raise AccessError(self.env._("Use the receivable deposit of this learner's course context."))
        if payload.submission_id.received_at >= member.learning_ends_at:
            self.env["training.elearning.practical.service"]._deposit_context(
                member.id, payload.submission_id.slide_id.id
            )
        return super(Attachment, self.sudo().with_context({}, image_no_postprocess=True)).create(
            {
                "name": item["name"],
                "raw": item["content"],
                "mimetype": item["mimetype"],
                "res_model": PAYLOAD,
                "res_id": payload.id,
                "public": False,
                "access_token": False,
            }
        )  # pylint: disable=super-method-mismatch,context-overridden

    @api.model
    def _access_domain(self, operation):
        domain = super()._access_domain(operation)
        if operation != "read":
            return domain
        for model, group in ((TASK, AUTHOR), (PAYLOAD, PEDAGOGY)):
            allowed = self.env.user.active and self.env.user.has_group(group)
            companies = (self.env.companies & self.env.user.company_ids).ids if allowed else []
            blocked = (
                self.env[model]
                .sudo()
                ._search(
                    ~self.env[model]._file_read_domain()
                    if model == PAYLOAD
                    else Domain("company_id", "not in", companies)
                )
            )
            domain &= ~(Domain("res_model", "=", model) & Domain("res_id", "any!", blocked))
        return domain

    def _to_http_stream(self):
        check_file(self)
        return super()._to_http_stream()


class Binary(models.AbstractModel):
    _inherit = "ir.binary"  # pylint: disable=consider-merging-classes-inherited

    def _find_record(self, xmlid=None, res_model="ir.attachment", res_id=None, access_token=None, field=None):
        record = super()._find_record(xmlid, res_model, res_id, access_token, field)
        check_file(record)
        return record

    def _get_stream_from(self, record, *args, **kwargs):
        check_file(record)
        return super()._get_stream_from(record, *args, **kwargs)
