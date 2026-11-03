"""Native discovery, completion and binary links never bypass the managed grant."""

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.http import request
from werkzeug.exceptions import NotFound
from .course import AUTHOR, MANAGER

MODELS = ("slide.channel", "slide.slide", "slide.channel.partner", "slide.slide.partner")


def course_for(record):
    target = record.sudo()
    if target._name == "ir.attachment" and target.res_model in MODELS:
        target = record.env[target.res_model].sudo().browse(target.res_id).exists()
    course = (
        target
        if target._name == "slide.channel"
        else target.channel_id
        if target._name in MODELS
        else record.env["slide.channel"]
    )
    return course.filtered("training_course_id")


def check_binary(record):
    course = course_for(record)
    target_model = record.sudo().res_model if record._name == "ir.attachment" else record._name
    group = MANAGER if target_model in MODELS[2:] else AUTHOR
    if course and (
        not record.env.user.active
        or not record.env.user.has_group(group)
        or any(c.learning_company_id not in record.env.companies for c in course)
    ):
        raise AccessError(record.env._("This private learning file is unavailable."))


class Binary(models.AbstractModel):
    _inherit = "ir.binary"

    def _find_record(self, xmlid=None, res_model="ir.attachment", res_id=None, access_token=None, field=None):
        record = super()._find_record(xmlid, res_model, res_id, access_token, field)
        check_binary(record)
        return record

    def _get_stream_from(self, record, *args, **kwargs):
        check_binary(record)
        return super()._get_stream_from(record, *args, **kwargs)


class Attachment(models.Model):
    _inherit = "ir.attachment"

    @api.model
    def _access_domain(self, operation):
        domain = super()._access_domain(operation)
        if operation != "read":
            return domain
        for model in MODELS:
            blocked = Domain("training_course_id", "!=", False)
            group = MANAGER if model in MODELS[2:] else AUTHOR
            if self.env.user.active and self.env.user.has_group(group):
                blocked &= Domain("learning_company_id", "not in", self.env.companies.ids)
            courses = self.env["slide.channel"].sudo()._search(blocked, active_test=False)
            records = (
                courses
                if model == "slide.channel"
                else self.env[model].sudo()._search(Domain("channel_id", "any!", courses), active_test=False)
            )
            domain &= ~(Domain("res_model", "=", model) & Domain("res_id", "any!", records))
        return domain

    def _to_http_stream(self):
        check_binary(self)
        return super()._to_http_stream()


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _match(cls, path_info):
        rule, values = super()._match(path_info)
        if not path_info.startswith(("/slides", "/slides_survey")):
            return rule, values
        # Native managed routes are closed even with an invitation hash. The
        # same native routes continue to serve unmanaged Community courses.
        params = dict(request.httprequest.args)
        params.update(request.httprequest.form)
        payload = request.httprequest.get_json(silent=True)
        if isinstance(payload, dict) and isinstance(payload.get("params"), dict):
            params.update(payload["params"])
        params.update(values)
        for key, model in (
            ("channel", "slide.channel"),
            ("channel_id", "slide.channel"),
            ("slide", "slide.slide"),
            ("slide_id", "slide.slide"),
        ):
            value = params.get(key)
            if not value:
                continue
            if getattr(value, "_name", None) == model:
                record = value
            else:
                try:
                    record = request.env[model].sudo().browse(int(value)).exists()
                except (TypeError, ValueError):
                    continue
            if record and course_for(record):
                raise NotFound()
        return rule, values
