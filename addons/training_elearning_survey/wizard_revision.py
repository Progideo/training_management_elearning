"""Explicit shared-version selection without changing existing learner obligations."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class Slide(models.Model):
    _inherit = "slide.slide"  # pylint: disable=consider-merging-classes-inherited
    learning_exam_revision_log = fields.Json(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if (
            any("learning_exam_revision_log" in vals for vals in vals_list)
            or "default_learning_exam_revision_log" in self.env.context
        ):
            raise AccessError(self.env._("Exam version changes are traced by the server."))
        return super().create(vals_list)

    def write(self, vals):
        if "learning_exam_revision_log" in vals:
            raise AccessError(self.env._("Keep the exam version change history."))
        return super().write(vals)

    def action_learning_exam_revision(self):
        self.ensure_one()
        self.channel_id._learning_staff()
        self.survey_id._mock_editor()
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.exam.revision",
            "view_mode": "form",
            "target": "new",
            "context": {"default_slide_id": self.id},
        }


class Revision(models.TransientModel):
    _name = "training.elearning.exam.revision"
    _description = "Select a New Shared Exam Version"
    slide_id = fields.Many2one("slide.slide", required=True)
    exam_id = fields.Many2one("survey.survey", required=True)
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        slide = self.slide_id
        course = slide.channel_id
        course._learning_staff()
        course._learning_lock_graph()
        slide.invalidate_recordset()
        old, new = slide.survey_id, self.exam_id
        (old | new)._mock_editor()
        if (
            not course.training_course_id
            or slide.slide_category != "certification"
            or not slide.active
            or not old
            or not new.active
            or new.training_state != "published"
            or new.training_course_id != course.training_course_id
            or new.mock_company_id != course.learning_company_id
            or (new.training_origin_id or new) != (old.training_origin_id or old)
            or new == old
            or not (self.reason or "").strip()
        ):
            raise ValidationError(
                self.env._("Choose a different published version of the same exam family and provide a reason.")
            )
        log = list(slide.learning_exam_revision_log or [])
        log.append(
            {
                "actor": self.env.uid,
                "at": fields.Datetime.to_string(fields.Datetime.now()),
                "before": old.id,
                "after": new.id,
                "reason": self.reason.strip(),
            }
        )
        slide._learning_store_version({"survey_id": new.id, "learning_exam_revision_log": log})
        return {"type": "ir.actions.act_window_close"}
