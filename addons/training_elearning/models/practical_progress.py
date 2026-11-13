"""Practical versions on native lessons and the existing native evidence rows."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import sql


def prepare_counter(model, name="nbr_learning_task"):
    # For a newly supported category there are no historical lessons. Add
    # the zero-valued nullable counter without recomputing native stored
    # statistics (and their audit dates) on every historical course/section.
    if sql.table_exists(model.env.cr, model._table) and not sql.column_exists(model.env.cr, model._table, name):
        sql.create_column(model.env.cr, model._table, name, "int4")


class Course(models.Model):
    _inherit = "slide.channel"  # pylint: disable=consider-merging-classes-inherited
    nbr_learning_task = fields.Integer(compute="_compute_slides_statistics", store=True)

    def _auto_init(self):
        prepare_counter(self)
        return super()._auto_init()


class Slide(models.Model):
    _inherit = "slide.slide"  # pylint: disable=consider-merging-classes-inherited
    nbr_learning_task = fields.Integer(compute="_compute_slides_statistics", store=True)

    def _auto_init(self):
        prepare_counter(self)
        return super()._auto_init()

    slide_category = fields.Selection(
        selection_add=[("learning_task", "Practical Work")], ondelete={"learning_task": "set default"}
    )
    learning_practical_revision_log = fields.Json(readonly=True, copy=False)
    learning_practical_id = fields.Many2one("training.elearning.practical", ondelete="restrict", copy=True)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if (
                "learning_practical_revision_log" in values
                or "default_learning_practical_revision_log" in self.env.context
            ):
                raise AccessError(self.env._("Practical version changes are traced by the server."))
            if values.get("learning_practical_id"):
                task = self.env["training.elearning.practical"].browse(values["learning_practical_id"])
                task.check_access("read")
                values.update(slide_category="learning_task", is_preview=False)
                values.setdefault("name", task.name)
        return super().create(vals_list)

    def write(self, values):
        if "learning_practical_revision_log" in values:
            raise AccessError(self.env._("Keep the practical version change history."))
        return super().write(values)

    def action_learning_practical_revision(self):
        self.ensure_one()
        self.channel_id._learning_staff()
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.practical.revision",
            "view_mode": "form",
            "target": "new",
            "context": {"default_slide_id": self.id},
        }

    @api.constrains("learning_practical_id", "slide_category", "channel_id", "is_published")
    def _check_practical_reference(self):
        if any(slide.slide_category == "learning_task" and not slide.channel_id.training_course_id for slide in self):
            raise ValidationError(self.env._("Practical work belongs to a private managed course edition."))
        for slide in self.filtered(
            lambda item: (
                item.channel_id.training_course_id
                and (item.learning_practical_id or item.slide_category == "learning_task")
            )
        ):
            task = slide.learning_practical_id
            if (
                not task
                or task.state != "published"
                or slide.slide_category != "learning_task"
                or task.training_course_id != slide.channel_id.training_course_id
                or task.company_id != slide.channel_id.learning_company_id
                or ("survey_id" in slide._fields and slide.survey_id)
            ):
                raise ValidationError(
                    self.env._("Choose one published practical version from this course and company.")
                )

    @api.private
    def _learning_supported(self):
        if self.slide_category != "learning_task":
            return super()._learning_supported()
        task = self.sudo().learning_practical_id
        return bool(
            self._learning_available()
            and task.state == "published"
            and task.training_course_id == self.channel_id.training_course_id
            and task.company_id == self.channel_id.learning_company_id
        )

    @api.private
    def _learning_plan_item(self):
        if self.slide_category != "learning_task":
            return super()._learning_plan_item()
        return {
            "id": self.id,
            "kind": "task",
            "task": self.learning_practical_id.id,
            "required": not self.learning_optional,
            "prerequisites": self.learning_prerequisite_ids.ids,
            "title": self.name,
        }


class Service(models.AbstractModel):
    _inherit = "training.elearning.service"  # pylint: disable=consider-merging-classes-inherited

    @api.private
    def _activity_url(self, member, item):
        if item["kind"] == "task":
            return "/my/learning/%s/tasks/%s" % (member.id, item["id"])
        return super()._activity_url(member, item)
