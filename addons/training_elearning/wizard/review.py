"""Native review forms bind the displayed candidate to the later server judgement."""

from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, ValidationError
from ..models.human_practical import PEDAGOGY, valid_reviewer


class ReviewWizard(models.TransientModel):
    _name = "training.elearning.review.wizard"
    _description = "Assess Current Practical Submission"
    queue_id = fields.Many2one("training.elearning.review.queue", required=True, readonly=True)
    submission_id = fields.Many2one("training.elearning.submission", required=True, readonly=True)
    outcome = fields.Selection([("validated", "Validate"), ("revision", "Request Revision")], required=True)
    feedback = fields.Text(required=True)
    line_ids = fields.One2many("training.elearning.review.wizard.line", "wizard_id")

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        queue = self.env["training.elearning.review.queue"].browse(values.get("queue_id") or self.env.context.get("default_queue_id"))
        if queue:
            queue._authorize(review=True)
            if queue.state != "pending":
                raise ValidationError(self.env._("Open the current pending practical candidate."))
            if "submission_id" in field_names:
                values["submission_id"] = queue.submission_id.id
            if "line_ids" in field_names:
                values["line_ids"] = [
                    Command.create({"criterion_id": line.id}) for line in queue.practical_id.rubric_ids
                ]
        return values

    def action_publish(self):
        self.ensure_one()
        if len(self.line_ids) != len(self.line_ids.criterion_id):
            raise ValidationError(self.env._("Assess every rubric criterion exactly once."))
        self.queue_id._publish(
            self.submission_id.id,
            self.outcome,
            {str(line.criterion_id.id): line.satisfied for line in self.line_ids},
            self.feedback,
        )
        return {"type": "ir.actions.act_window_close"}


class ReviewLine(models.TransientModel):
    _name = "training.elearning.review.wizard.line"
    _description = "Current Practical Criterion Judgement"
    wizard_id = fields.Many2one("training.elearning.review.wizard", required=True, ondelete="cascade")
    criterion_id = fields.Many2one("training.elearning.practical.rubric", required=True, readonly=True)
    description = fields.Text(related="criterion_id.description")
    required = fields.Boolean(related="criterion_id.required")
    satisfied = fields.Boolean()


class Reassignment(models.TransientModel):
    _name = "training.elearning.review.reassign"
    _description = "Motivated Practical Reviewer Reassignment"
    queue_id = fields.Many2one("training.elearning.review.queue", required=True, readonly=True)
    reviewer_id = fields.Many2one("res.users", required=True)
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        self.queue_id._reassign(self.reviewer_id, self.reason)
        return {"type": "ir.actions.act_window_close"}


class ReviewerSetup(models.TransientModel):
    _name = "training.elearning.reviewer.setup"
    _description = "Motivated Default Practical Reviewer Change"
    course_id = fields.Many2one("slide.channel")
    slide_id = fields.Many2one("slide.slide")
    reviewer_id = fields.Many2one("res.users", required=True)
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        if bool(self.course_id) == bool(self.slide_id):
            raise ValidationError(self.env._("Choose one course default or one practical exception."))
        course = self.course_id or self.slide_id.channel_id
        course._learning_staff(manager=True)
        if not self.env.user.has_group(PEDAGOGY):
            raise AccessError(self.env._("Pedagogical coordination permission is required."))
        course._learning_lock_graph()
        if not (self.reason or "").strip() or not valid_reviewer(self.reviewer_id, course.learning_company_id):
            raise ValidationError(self.env._("Choose an active authorized reviewer and explain the change."))
        target = self.slide_id or course
        if self.slide_id and self.slide_id.learning_practical_id.criterion != "human":
            raise ValidationError(self.env._("Choose a human-reviewed practical activity."))
        log = list(target.learning_reviewer_log or [])
        log.append(
            {
                "actor": self.env.uid,
                "at": fields.Datetime.to_string(fields.Datetime.now()),
                "before": target.learning_reviewer_id.id,
                "after": self.reviewer_id.id,
                "reason": self.reason.strip(),
            }
        )
        values = {"learning_reviewer_id": self.reviewer_id.id, "learning_reviewer_log": log}
        if self.slide_id:
            self.slide_id._learning_store_version(values)
        else:
            course._learning_store_reviewer(values)
        return {"type": "ir.actions.act_window_close"}


class DeliveryResolution(models.TransientModel):
    _name = "training.elearning.review.delivery"
    _description = "Resolve Practical Feedback Delivery"
    notice_id = fields.Many2one("training.elearning.review.notice", required=True, readonly=True)
    reason = fields.Text(required=True)
    manual = fields.Boolean(string="Agreed Alternative Channel")

    def action_apply(self):
        self.ensure_one()
        notice_id = self.notice_id.action_retry(reason=self.reason, manual=self.manual)
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.review.notice",
            "res_id": notice_id,
            "view_mode": "form",
            "target": "current",
        }
