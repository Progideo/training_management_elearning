"""Native supplementary resources, bound to the existing immutable course graph."""
import hashlib
import io
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from PIL import Image
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.addons.training_elearning.models.course import AUTHOR

MAX_BYTES = 64 * 1024 * 1024
MIMES = {
    ".zip": "application/zip",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".png": "image/png", ".gif": "image/gif", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".pdf": "application/pdf",
}


def blocked_courses(env):
    domain = Domain("training_course_id", "!=", False)
    if env.user.active and env.user.has_group(AUTHOR):
        domain &= Domain("learning_company_id", "not in", env.companies.ids)
    return env["slide.channel"].sudo()._search(domain, active_test=False)


def validate_link(link, env):
    try:
        value = urlsplit(link or "")
        valid = (value.scheme in ("http", "https") and value.hostname and not value.username
                 and not value.password and not any(ord(c) <= 32 for c in link))
        value.port
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise ValidationError(env._("Use an absolute HTTP(S) link without credentials or whitespace."))


class Resource(models.Model):
    _inherit = "slide.slide.resource"

    @api.model
    def _access_domain(self, operation):
        domain = super()._access_domain(operation)
        # Native membership ACLs alone do not enforce the autonomous grant deadline.
        slides = self.env["slide.slide"].sudo()._search(
            Domain("channel_id", "any!", blocked_courses(self.env)), active_test=False)
        return domain & ~Domain("slide_id", "any!", slides)

    @api.private
    def _resource_edit(self, values=None):
        values = values or {}
        slides = self.sudo().slide_id
        slide_id = values.get("slide_id", self.env.context.get("default_slide_id"))
        if slide_id:
            slides |= self.env["slide.slide"].sudo().browse(slide_id).exists()
        courses = slides.channel_id.filtered("training_course_id").with_env(self.env)
        if courses:
            courses._learning_staff()
            courses._learning_before_revision()
            if courses._learning_frozen():
                raise ValidationError(self.env._("Create a new course edition to change its supplementary resources."))
            # Touch the locked parent: concurrent Repeatable Read activation must retry
            # rather than freeze a snapshot preceding this resource edit.
            courses.write({"write_date": fields.Datetime.now()})
        return courses

    @api.private
    def _resource_snapshot(self):
        self.ensure_one()
        row = {"id": self.id, "name": self.name or self.file_name or self.link,
               "type": self.resource_type}
        if self.resource_type == "url":
            validate_link(self.link, self.env)
            return dict(row, link=self.link)
        name = self.file_name or ""
        ext = PurePosixPath(name).suffix.lower()
        if (ext not in MIMES or not name or name != PurePosixPath(name).name
                or "\\" in name or any(ord(c) < 32 or ord(c) == 127 for c in name)):
            raise ValidationError(self.env._("Choose a ZIP, Excel, PNG, GIF, JPEG or PDF file with a simple filename."))
        data = self.with_context(bin_size=False).data
        body = data.content if data else b""
        if not body or len(body) > MAX_BYTES:
            raise ValidationError(self.env._("Choose a nonempty file no larger than 64 MiB."))
        try:
            if ext in (".zip", ".xlsx"):
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    # No extraction, execution, metadata fetch or decompression of ZIP contents.
                    if ext == ".xlsx" and not {"[Content_Types].xml", "xl/workbook.xml"} <= set(archive.namelist()):
                        raise ValueError("Not an XLSX workbook")
            elif ext == ".xls":
                if not body.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
                    raise ValueError("Not an OLE workbook")
            elif ext == ".pdf":
                if not body.startswith(b"%PDF-"):
                    raise ValueError("Not a PDF")
            else:
                with Image.open(io.BytesIO(body)) as image:
                    if image.format != {".png": "PNG", ".gif": "GIF", ".jpg": "JPEG", ".jpeg": "JPEG"}[ext]:
                        raise ValueError("Unexpected image format")
                    image.verify()
        except (ValueError, OSError, zipfile.BadZipFile, Image.DecompressionBombError) as error:
            raise ValidationError(self.env._("The file does not match its declared format.")) from error
        return dict(row, filename=name, mimetype=MIMES[ext], size=len(body), sha256=hashlib.sha256(body).hexdigest())

    @api.constrains("slide_id", "resource_type", "data", "file_name", "link", "name")
    def _check_managed_resource(self):
        for resource in self.filtered(lambda r: r.slide_id.channel_id.training_course_id):
            resource._resource_snapshot()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self.browse()._resource_edit(values)
        return super().create(vals_list)

    def write(self, values):
        self._resource_edit(values)
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _keep_bound_resource(self):
        self._resource_edit()


class Course(models.Model):
    _inherit = "slide.channel"

    @api.private
    def _learning_plan(self):
        plan = super()._learning_plan()
        for item in plan["slides"]:
            resources = self.env["slide.slide.resource"].sudo().search([("slide_id", "=", item["id"])])
            item["resources"] = [resource._resource_snapshot() for resource in resources]
        return plan
