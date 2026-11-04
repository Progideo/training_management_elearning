# pylint: disable=super-method-mismatch  # checked private transitions bypass public mutation guards
"""Versioned practical instructions on the shared catalogue, without a second course."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .submission_files import DEFAULT_EXTENSIONS, InvalidSubmission, extensions

AUTHOR = "training_elearning.group_elearning_author"
LIMITS = {
    "learning_submission_extensions",
    "learning_submission_max_files",
    "learning_submission_file_mib",
    "learning_submission_total_mib",
}


class Company(models.Model):
    _inherit = "res.company"
    learning_submission_extensions = fields.Char(default=DEFAULT_EXTENSIONS)
    learning_submission_max_files = fields.Integer(default=5)
    learning_submission_file_mib = fields.Integer(default=20)
    learning_submission_total_mib = fields.Integer(default=50)

    def write(self, values):
        if LIMITS & values.keys() and (not self.env.user.active or not self.env.user.has_group("base.group_system")):
            raise AccessError(self.env._("Only an active administrator configures practical upload ceilings."))
        return super().write(values)

    @api.constrains(*sorted(LIMITS))
    def _check_learning_upload_policy(self):
        for company in self:
            try:
                extensions(company.learning_submission_extensions)
            except InvalidSubmission as error:
                raise ValidationError(
                    self.env._("Choose file extensions supported by the practical format validator.")
                ) from error
            if (
                company.learning_submission_max_files <= 0
                or company.learning_submission_max_files > 100
                or company.learning_submission_file_mib <= 0
                or company.learning_submission_total_mib < company.learning_submission_file_mib
                or company.learning_submission_total_mib > 100
            ):
                raise ValidationError(
                    self.env._(
                        "Choose positive upload ceilings: at most 100 files and 100 MiB total, with the total at least as large as one file."
                    )
                )


class Practical(models.Model):
    _name = "training.elearning.practical"
    _description = "Versioned Practical Work Definition"
    _rec_name = "name"
    name = fields.Char(required=True)
    training_course_id = fields.Many2one("training.course", required=True, ondelete="restrict", copy=True)
    company_id = fields.Many2one(related="training_course_id.company_id")
    origin_id = fields.Many2one("training.elearning.practical", readonly=True, ondelete="restrict", copy=False)
    version_ref = fields.Char(default="1", copy=False)
    revision_reason = fields.Text(copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("published", "Published")], default="draft", readonly=True, copy=False
    )
    published_at = fields.Datetime(readonly=True, copy=False)
    criterion = fields.Selection(
        [("self", "Self-assessment Declaration"), ("deposit", "Receivable File Submission")],
        required=True,
        default="self",
    )
    instructions = fields.Text(required=True)
    upload_extensions = fields.Char(default=DEFAULT_EXTENSIONS)
    max_files = fields.Integer(default=5)
    file_mib = fields.Integer(default=20)
    total_mib = fields.Integer(default=50)
    _unique_version = models.UniqueIndex(
        "(COALESCE(origin_id, id), version_ref) WHERE version_ref IS NOT NULL",
        "This practical version reference already exists.",
    )

    @api.private
    def _staff(self):
        if not self.env.user.active or not self.env.user.has_group(AUTHOR):
            raise AccessError(self.env._("Practical author permission is required."))
        self.check_access("write")
        if any(
            item.company_id not in self.env.companies or item.company_id not in self.env.user.company_ids
            for item in self
        ):
            raise AccessError(self.env._("Use practical definitions in your active companies."))

    @api.private
    def _policy(self):
        self.ensure_one()
        return {
            "extensions": self.upload_extensions,
            "files": self.max_files,
            "file_mib": self.file_mib,
            "total_mib": self.total_mib,
        }

    @api.private
    def _defaults_for(self, course):
        return {
            "max_files": course.company_id.learning_submission_max_files,
            "file_mib": course.company_id.learning_submission_file_mib,
            "total_mib": course.company_id.learning_submission_total_mib,
            "upload_extensions": course.company_id.learning_submission_extensions,
        }

    @api.model_create_multi
    def create(self, vals_list):
        self._staff()
        for values in vals_list:
            if {"origin_id", "published_at"} & values.keys() or any(
                "default_" + key in self.env.context for key in ("origin_id", "published_at")
            ):
                raise AccessError(self.env._("Create practical versions through the controlled version action."))
            if values.get("state", self.env.context.get("default_state", "draft")) != "draft":
                raise AccessError(self.env._("Publish the practical through its controlled action."))
            course = self.env["training.course"].browse(
                values.get("training_course_id") or self.env.context.get("default_training_course_id")
            )
            course.check_access("read")
            if (
                not course
                or course.company_id not in self.env.companies
                or course.company_id not in self.env.user.company_ids
            ):
                raise AccessError(self.env._("Choose a catalogue entry in your active companies."))
            course.lock_for_update()
            for name, default in self._defaults_for(course).items():
                values.setdefault(name, self.env.context.get("default_" + name, default))
        return super().create(vals_list)

    def write(self, values):
        self._staff()
        self.lock_for_update()
        self.invalidate_recordset()
        if {"origin_id", "published_at", "state", "training_course_id"} & values.keys():
            raise AccessError(self.env._("Keep the practical identity and use its publication/version actions."))
        if any(item.state == "published" for item in self):
            raise ValidationError(self.env._("Published practical definitions are immutable; create a new version."))
        return super().write(values)

    @api.constrains("upload_extensions", "max_files", "file_mib", "total_mib", "training_course_id")
    def _check_limits(self):
        for item in self:
            try:
                selected = extensions(item.upload_extensions)
                ceiling = extensions(item.company_id.learning_submission_extensions)
            except InvalidSubmission as error:
                raise ValidationError(self.env._("Choose supported practical upload formats.")) from error
            if (
                not selected <= ceiling
                or item.max_files <= 0
                or item.max_files > item.company_id.learning_submission_max_files
                or item.file_mib <= 0
                or item.file_mib > item.company_id.learning_submission_file_mib
                or item.total_mib < item.file_mib
                or item.total_mib > item.company_id.learning_submission_total_mib
            ):
                raise ValidationError(self.env._("Use file limits no greater than the organization ceilings."))

    def action_publish(self):  # pylint: disable=super-method-mismatch
        self._staff()
        self.lock_for_update()
        self.invalidate_recordset()
        drafts = self.filtered(lambda item: item.state != "published")
        for item in drafts:
            item._check_limits()
            if not (item.version_ref or "").strip() or not (item.instructions or "").strip():
                raise ValidationError(self.env._("Provide the version reference and practical instructions."))
            if item.origin_id and (
                not (item.revision_reason or "").strip() or item.criterion != item.origin_id.criterion
            ):
                raise ValidationError(self.env._("Explain the version change and keep its completion criterion."))
        return (
            super(Practical, drafts).write({"state": "published", "published_at": fields.Datetime.now()})
            if drafts
            else True
        )

    def action_new_version(self):
        self.ensure_one()
        self._staff()
        self.lock_for_update()
        if self.state != "published":
            raise ValidationError(self.env._("Publish this practical version first."))
        values = self.copy_data()[0]
        values.update(
            origin_id=(self.origin_id or self).id,
            state="draft",
            published_at=False,
            version_ref=False,
            revision_reason=False,
        )
        ceiling = self._defaults_for(self.training_course_id)
        for name in ("max_files", "file_mib", "total_mib"):
            values[name] = min(values[name], ceiling[name])
        selected = extensions(values["upload_extensions"]) & extensions(ceiling["upload_extensions"])
        values["upload_extensions"] = ",".join(sorted(selected)) if selected else ceiling["upload_extensions"]
        new = super(Practical, self.sudo().with_context({})).create(values)  # pylint: disable=super-method-mismatch,context-overridden
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": new.id, "view_mode": "form"}

    @api.ondelete(at_uninstall=False)
    def _keep_practicals(self):
        if any(item.state == "published" or item.origin_id for item in self):
            raise ValidationError(self.env._("Keep published practical versions and their history."))


class Catalog(models.Model):
    _inherit = "training.course"  # pylint: disable=consider-merging-classes-inherited

    def write(self, values):
        if "company_id" in values and any(item.company_id.id != values["company_id"] for item in self):
            self.lock_for_update()
            if self.env["training.elearning.practical"].sudo().search_count([("training_course_id", "in", self.ids)]):
                raise ValidationError(self.env._("Keep the operating company of referenced practical definitions."))
        return super().write(values)
