# pylint: disable=super-method-mismatch,context-overridden
"""Frozen practical rubrics and explicit active reviewer configuration."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .submission import PEDAGOGY

REVIEWER = "training_elearning.group_elearning_reviewer"


def coordinator(records):
    user = records.env.user
    if not user.active or not user.has_group(PEDAGOGY):
        raise AccessError(records.env._("Pedagogical coordination permission is required."))
    records.check_access("write")


def valid_reviewer(user, company, learner=None):
    user = user.sudo()
    return bool(
        user
        and user.active
        and not user.share
        and user.has_group(REVIEWER)
        and company in user.company_ids
        and user != learner
    )


class Practical(models.Model):
    _inherit = "training.elearning.practical"
    criterion = fields.Selection(selection_add=[("human", "Human Review")], ondelete={"human": "set default"})
    rubric_ids = fields.One2many("training.elearning.practical.rubric", "practical_id", copy=True)
    review_queue_ids = fields.One2many("training.elearning.review.queue", "practical_id")

    def action_publish(self):
        for task in self.filtered(lambda item: item.criterion == "human" and item.state != "published"):
            if not task.rubric_ids or any(not (line.description or "").strip() for line in task.rubric_ids):
                raise ValidationError(
                    self.env._("Provide a nonempty review rubric with clear criteria before publication.")
                )
        return super().action_publish()


class Rubric(models.Model):
    _name = "training.elearning.practical.rubric"
    _description = "Versioned Practical Review Criterion"
    _order = "sequence, id"
    practical_id = fields.Many2one("training.elearning.practical", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="practical_id.company_id")
    sequence = fields.Integer(default=10)
    description = fields.Text(required=True)
    required = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            task = self.env["training.elearning.practical"].browse(
                values.get("practical_id") or self.env.context.get("default_practical_id")
            )
            task._staff()
            task.lock_for_update()
            if not task or task.state != "draft":
                raise ValidationError(self.env._("Edit only the rubric of a draft practical version."))
        return super().create(vals_list)

    def write(self, values):
        tasks = self.practical_id | self.env["training.elearning.practical"].browse(values.get("practical_id"))
        tasks._staff()
        tasks.lock_for_update()
        if any(task.state != "draft" for task in tasks):
            raise ValidationError(self.env._("Keep published practical rubrics."))
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _keep_rubric(self):
        self.practical_id._staff()
        self.practical_id.lock_for_update()
        if any(task.state != "draft" for task in self.practical_id):
            raise ValidationError(self.env._("Keep published practical rubrics."))


class Course(models.Model):
    _inherit = "slide.channel"
    learning_reviewer_id = fields.Many2one("res.users", ondelete="restrict", copy=True)
    learning_review_calendar_id = fields.Many2one("resource.calendar", readonly=True, ondelete="restrict", copy=False)
    learning_reviewer_log = fields.Json(readonly=True, copy=False)
    learning_review_days = fields.Integer(default=5)
    learning_revision_days = fields.Integer(default=14)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if {"learning_review_calendar_id", "learning_reviewer_log"} & values.keys() or any(
                "default_" + name in self.env.context
                for name in ("learning_review_calendar_id", "learning_reviewer_log")
            ):
                raise AccessError(self.env._("The server freezes practical review policies."))
            if values.get("learning_reviewer_id") or self.env.context.get("default_learning_reviewer_id"):
                coordinator(self)
        return super().create(vals_list)

    def write(self, values):
        if {"learning_review_calendar_id", "learning_reviewer_log"} & values.keys():
            raise AccessError(self.env._("Keep the frozen review policy and reassignment history."))
        if {"learning_reviewer_id", "learning_review_days", "learning_revision_days"} & values.keys():
            coordinator(self)
            self._learning_lock_graph()
            if self._learning_frozen():
                raise ValidationError(
                    self.env._("Use an explicit reviewer reassignment; keep the contractual review durations.")
                )
        return super().write(values)

    def action_learning_reviewer_setup(self):
        self.ensure_one()
        self._learning_staff(manager=True)
        if not self.env.user.has_group(PEDAGOGY):
            raise AccessError(self.env._("Pedagogical coordination permission is required."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.reviewer.setup",
            "view_mode": "form",
            "target": "new",
            "context": {"default_course_id": self.id},
        }

    @api.private
    def _learning_store_reviewer(self, values):
        self.ensure_one()
        self._learning_staff(manager=True)
        if not self.env.user.has_group(PEDAGOGY) or set(values) != {"learning_reviewer_id", "learning_reviewer_log"}:
            raise AccessError(self.env._("Use the explicit pedagogical reviewer change."))
        return super(Course, self).write(values)

    @api.constrains("learning_review_days", "learning_revision_days")
    def _check_review_durations(self):
        if any(not 0 < c.learning_review_days <= 365 or not 0 < c.learning_revision_days <= 365 for c in self):
            raise ValidationError(self.env._("Choose review and revision delays between 1 and 365 days."))

    def action_learning_publish(self):
        self._learning_staff()
        self.lock_for_update()
        for course in self:
            if (
                course.slide_ids.filtered(lambda s: s.learning_practical_id.criterion == "human")
                and not course.learning_review_calendar_id
            ):
                calendar = course.learning_company_id.sudo().resource_calendar_id._learning_snapshot(course)
                super(Course, course).write({"learning_review_calendar_id": calendar.id})
        return super().action_learning_publish()

    @api.private
    def _learning_check_contents(self):
        result = super()._learning_check_contents()
        for slide in self.slide_ids.filtered(lambda s: s.learning_practical_id.criterion == "human"):
            slide._learning_check_reviewer()
            if not slide.channel_id.learning_review_calendar_id.learning_review_snapshot:
                raise ValidationError(
                    self.env._("Publish the practical contract calendar before offering this course.")
                )
        return result

    @api.private
    def _learning_plan(self):
        plan = super()._learning_plan()
        for item in plan["slides"]:
            if (
                item.get("kind") == "task"
                and self.env["training.elearning.practical"].sudo().browse(item["task"]).criterion == "human"
            ):
                item.update(
                    review_calendar=self.learning_review_calendar_id.id,
                    review_days=self.learning_review_days,
                    revision_days=self.learning_revision_days,
                )
        return plan


class Slide(models.Model):
    _inherit = "slide.slide"
    learning_reviewer_id = fields.Many2one("res.users", ondelete="restrict", copy=True)
    learning_reviewer_log = fields.Json(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if "learning_reviewer_log" in values or "default_learning_reviewer_log" in self.env.context:
                raise AccessError(self.env._("Keep the server reviewer history."))
            if values.get("learning_reviewer_id") or self.env.context.get("default_learning_reviewer_id"):
                coordinator(self)
        return super().create(vals_list)

    def write(self, values):
        if "learning_reviewer_log" in values:
            raise AccessError(self.env._("Keep the server reviewer history."))
        if "learning_reviewer_id" in values:
            coordinator(self)
        return super().write(values)

    def action_learning_reviewer_setup(self):
        self.ensure_one()
        self.channel_id._learning_staff(manager=True)
        if not self.env.user.has_group(PEDAGOGY):
            raise AccessError(self.env._("Pedagogical coordination permission is required."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.reviewer.setup",
            "view_mode": "form",
            "target": "new",
            "context": {"default_slide_id": self.id},
        }

    @api.private
    def _learning_check_reviewer(self, learner=None):
        self.ensure_one()
        reviewer = self.sudo().learning_reviewer_id or self.sudo().channel_id.learning_reviewer_id
        if not valid_reviewer(reviewer, self.channel_id.learning_company_id, learner):
            raise ValidationError(
                self.env._("Assign an active authorized reviewer of this company, distinct from the learner.")
            )
        return reviewer
