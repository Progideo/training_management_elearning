from odoo import fields, models
from odoo.exceptions import ValidationError


class PracticalRevision(models.TransientModel):
    _name = "training.elearning.practical.revision"
    _description = "Explicit Practical Version Selection"
    slide_id = fields.Many2one("slide.slide", required=True)
    practical_id = fields.Many2one("training.elearning.practical", required=True)
    reason = fields.Text(required=True)

    def action_apply(self):
        self.ensure_one()
        slide = self.slide_id
        slide.channel_id._learning_staff()
        slide.channel_id._learning_lock_graph()
        slide.invalidate_recordset()
        old, new = slide.learning_practical_id, self.practical_id
        new._staff()
        if (
            not old
            or not slide.channel_id.training_course_id
            or new.state != "published"
            or new == old
            or new.company_id != slide.channel_id.learning_company_id
            or new.training_course_id != slide.channel_id.training_course_id
            or (new.origin_id or new) != (old.origin_id or old)
            or new.criterion != old.criterion
            or not (self.reason or "").strip()
        ):
            raise ValidationError(
                self.env._(
                    "Choose another published version of the same practical family and criterion; provide a reason."
                )
            )
        log = list(slide.learning_practical_revision_log or [])
        log.append(
            {
                "actor": self.env.uid,
                "at": fields.Datetime.to_string(fields.Datetime.now()),
                "before": old.id,
                "after": new.id,
                "reason": self.reason.strip(),
            }
        )
        slide._learning_store_version({"learning_practical_id": new.id, "learning_practical_revision_log": log})
        return {"type": "ir.actions.act_window_close"}
