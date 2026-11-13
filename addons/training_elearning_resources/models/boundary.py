"""Close raw binary/RPC paths; only the contextual service serves learner bytes."""
from odoo import api, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from odoo.addons.training_elearning.models.course import AUTHOR
from .resource import blocked_courses


def resource_for(record):
    target = record.sudo()
    if target._name == "ir.attachment" and target.res_model == "slide.slide.resource":
        target = record.env["slide.slide.resource"].sudo().browse(target.res_id).exists()
    return target if target._name == "slide.slide.resource" else record.env["slide.slide.resource"]


def check_resource(record):
    resources = resource_for(record)
    courses = resources.slide_id.channel_id.filtered("training_course_id")
    if courses and (not record.env.user.active or not record.env.user.has_group(AUTHOR)
                    or any(c.learning_company_id not in record.env.companies for c in courses)):
        raise AccessError(record.env._("This private supplementary resource is unavailable."))


class Binary(models.AbstractModel):
    _inherit = "ir.binary"

    def _find_record(self, xmlid=None, res_model="ir.attachment", res_id=None, access_token=None, field=None):
        record = super()._find_record(xmlid, res_model, res_id, access_token, field)
        check_resource(record)
        return record

    def _get_stream_from(self, record, *args, **kwargs):
        check_resource(record)
        return super()._get_stream_from(record, *args, **kwargs)


class Attachment(models.Model):
    _inherit = "ir.attachment"

    @api.private
    def _resource_guard(self, values=None):
        values = values or {}
        resources = self.env["slide.slide.resource"]
        for attachment in self.sudo():
            resources |= resource_for(attachment)
            if values.get("res_model", attachment.res_model) == "slide.slide.resource":
                resources |= resources.sudo().browse(values.get("res_id", attachment.res_id)).exists()
        if not self and values.get("res_model", self.env.context.get("default_res_model")) == "slide.slide.resource":
            resources |= resources.sudo().browse(values.get("res_id", self.env.context.get("default_res_id"))).exists()
        resources.with_env(self.env)._resource_edit()
        if resources.slide_id.channel_id.filtered("training_course_id") and (values.get("public", self.env.context.get("default_public"))
                or values.get("access_token", self.env.context.get("default_access_token"))):
            raise ValidationError(self.env._("Supplementary resources must remain private without bearer tokens."))

    @api.model
    def _postprocess_contents(self, values):
        # Native attachment creation resizes large PNG/JPEG images. Supplemental
        # files are downloads, so preserve their bytes; do not change other files.
        targets = [
            (values.get("res_model", record.res_model), values.get("res_id", record.res_id))
            for record in self.sudo()
        ] or [(values.get("res_model", self.env.context.get("default_res_model")),
               values.get("res_id", self.env.context.get("default_res_id")))]
        managed = [bool(self.env["slide.slide.resource"].sudo().browse(res_id).exists()
                        .slide_id.channel_id.training_course_id)
                   if model == "slide.slide.resource" and res_id else False for model, res_id in targets]
        if any(managed):
            if not all(managed):
                raise ValidationError(self.env._("Update private supplementary files separately from other attachments."))
            return values
        return super()._postprocess_contents(values)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self.browse()._resource_guard(values)
        return super().create(vals_list)

    def write(self, values):
        self._resource_guard(values)
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _keep_resource_file(self):
        self._resource_guard()

    @api.model
    def _access_domain(self, operation):
        domain = super()._access_domain(operation)
        if operation == "read":
            resources = self.env["slide.slide.resource"].sudo()._search(
                Domain("slide_id.channel_id", "any!", blocked_courses(self.env)), active_test=False)
            domain &= ~(Domain("res_model", "=", "slide.slide.resource") & Domain("res_id", "any!", resources))
        return domain

    def _to_http_stream(self):
        check_resource(self)
        return super()._to_http_stream()
