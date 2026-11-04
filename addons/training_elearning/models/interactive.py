# pylint: disable=consider-merging-classes-inherited  # reader guards are separate from scalar history
"""Native lesson bindings to the common immutable interactive package versions."""

import math
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .practical_progress import prepare_counter


class Course(models.Model):
    _inherit = "slide.channel"
    nbr_learning_interactive = fields.Integer(compute="_compute_slides_statistics", store=True)

    def _auto_init(self):
        prepare_counter(self, "nbr_learning_interactive")
        return super()._auto_init()


class Slide(models.Model):
    _inherit = "slide.slide"
    nbr_learning_interactive = fields.Integer(compute="_compute_slides_statistics", store=True)
    slide_category = fields.Selection(
        selection_add=[("learning_interactive", "Activité interactive")],
        ondelete={"learning_interactive": "set default"},
    )
    learning_interactive_version_id = fields.Many2one(
        "training.elearning.version", string="Version interactive publiée", ondelete="restrict"
    )
    learning_interactive_rule = fields.Selection(
        [("completed", "À terminer (formatif)"), ("score", "À terminer avec un seuil (formatif)")],
        default="completed",
        required=True,
    )
    learning_interactive_threshold = fields.Float(default=70, string="Seuil formatif (%)")
    learning_interactive_revision_log = fields.Json(readonly=True, copy=False)

    def _auto_init(self):
        prepare_counter(self, "nbr_learning_interactive")
        return super()._auto_init()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if (
                "learning_interactive_revision_log" in values
                or "default_learning_interactive_revision_log" in self.env.context
            ):
                raise AccessError(self.env._("Interactive version revisions are recorded by the server."))
            if values.get("learning_interactive_version_id"):
                version = self.env["training.elearning.version"].browse(values["learning_interactive_version_id"])
                version.check_access("read")
                values.update(slide_category="learning_interactive", is_preview=False)
                values.setdefault("name", version.resource_id.name)
        return super().create(vals_list)

    def write(self, values):
        if "learning_interactive_revision_log" in values:
            raise AccessError(self.env._("Keep interactive version revision history."))
        return super().write(values)

    @api.constrains(
        "learning_interactive_version_id",
        "learning_interactive_rule",
        "learning_interactive_threshold",
        "channel_id",
        "slide_category",
    )
    def _check_interactive(self):
        for slide in self.filtered(
            lambda row: row.learning_interactive_version_id or row.slide_category == "learning_interactive"
        ):
            version = slide.learning_interactive_version_id
            if (
                not slide.channel_id.training_course_id
                or not version
                or version.state != "published"
                or version.company_id != slide.channel_id.learning_company_id
                or slide.slide_category != "learning_interactive"
                or ("survey_id" in slide._fields and slide.survey_id)
                or slide.learning_practical_id
                or not math.isfinite(slide.learning_interactive_threshold)
                or not 0 <= slide.learning_interactive_threshold <= 100
            ):
                raise ValidationError(
                    self.env._(
                        "Choose one published interactive version in this managed course company and a valid formative threshold."
                    )
                )

    @api.private
    def _learning_supported(self):
        if self.slide_category != "learning_interactive":
            return super()._learning_supported()
        version = self.sudo().learning_interactive_version_id
        return bool(
            self._learning_available()
            and version.state == "published"
            and version.company_id == self.channel_id.learning_company_id
        )

    @api.private
    def _learning_plan_item(self):
        if self.slide_category != "learning_interactive":
            return super()._learning_plan_item()
        return {
            "id": self.id,
            "kind": "interactive",
            "version": self.learning_interactive_version_id.id,
            "rule": self.learning_interactive_rule,
            "threshold": self.learning_interactive_threshold,
            "required": not self.learning_optional,
            "prerequisites": self.learning_prerequisite_ids.ids,
            "title": self.name,
        }

    def action_learning_interactive_revision(self):
        self.ensure_one()
        self.channel_id._learning_staff()
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.interactive.revision",
            "view_mode": "form",
            "target": "new",
            "context": {"default_slide_id": self.id},
        }


class Membership(models.Model):
    _inherit = "slide.channel.partner"
    learning_interactive_revision = fields.Integer(readonly=True, copy=False)

    @api.private
    def _interactive_touch(self):
        self._learning_store({"learning_interactive_revision": self.sudo().learning_interactive_revision + 1})
        self.flush_recordset(["learning_interactive_revision"])


class Service(models.AbstractModel):
    _inherit = "training.elearning.service"

    @api.private
    def _activity_url(self, member, item):
        if item["kind"] == "interactive":
            return "/my/learning/%s/interactive/%s" % (member.id, item["id"])
        return super()._activity_url(member, item)

    @api.private
    def _activity(self, membership_id, slide_id, *, lock=False):
        member, slide, item = super()._activity(membership_id, slide_id, lock=lock)
        if item["kind"] == "interactive":
            version = self.env["training.elearning.version"].sudo().browse(item.get("version")).exists()
            if (
                not version
                or version.state != "published"
                or version.company_id != member.channel_id.learning_company_id
            ):
                raise AccessError(self.env._("This frozen interactive version is unavailable."))
        return member, slide, item

    @api.private
    def _item_status(self, member, item):
        status = super()._item_status(member, item)
        if item["kind"] == "interactive":
            version = self.env["training.elearning.version"].sudo().browse(item.get("version")).exists()
            unavailable = status["unavailable"] or not version or version.state != "published"
            status.update(unavailable=bool(unavailable))
            if unavailable and not status["complete"]:
                status["state"] = "unavailable"
        return status
