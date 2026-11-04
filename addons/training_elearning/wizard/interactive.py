"""A new evaluated package version preserves existing members' frozen lesson plans."""

import math
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Revision(models.TransientModel):
    _name = "training.elearning.interactive.revision"
    _description = "Motivated Interactive Lesson Version Revision"
    slide_id = fields.Many2one("slide.slide", required=True, readonly=True)
    version_id = fields.Many2one("training.elearning.version", required=True)
    threshold = fields.Float(required=True)
    reason = fields.Text(required=True)

    @api.model
    def default_get(self, names):
        values = super().default_get(names)
        slide = self.env["slide.slide"].browse(values.get("slide_id"))
        if slide:
            slide.channel_id._learning_staff()
            values.update(
                version_id=slide.learning_interactive_version_id.id, threshold=slide.learning_interactive_threshold
            )
        return {key: value for key, value in values.items() if key in names}

    def action_apply(self):
        self.ensure_one()
        slide, version = self.slide_id, self.version_id
        slide.channel_id._learning_staff()
        slide.channel_id._learning_before_revision()
        slide.lock_for_update()
        slide.invalidate_recordset()
        version.check_access("read")
        old = slide.learning_interactive_version_id
        if (
            not old
            or slide.slide_category != "learning_interactive"
            or version == old
            or version.resource_id != old.resource_id
            or version.company_id != old.company_id
            or version.state != "published"
            or not (self.reason or "").strip()
            or not math.isfinite(self.threshold)
            or not 0 <= self.threshold <= 100
        ):
            raise ValidationError(
                self.env._("Choose another published version of the same resource, a valid threshold and a reason.")
            )
        trace = {
            "at": fields.Datetime.to_string(fields.Datetime.now()),
            "actor": self.env.uid,
            "before": old.id,
            "after": version.id,
            "before_threshold": slide.learning_interactive_threshold,
            "after_threshold": self.threshold,
            "reason": self.reason.strip(),
        }
        slide._learning_store_version(
            {
                "learning_interactive_version_id": version.id,
                "learning_interactive_threshold": self.threshold,
                "learning_interactive_revision_log": list(slide.learning_interactive_revision_log or []) + [trace],
            }
        )
        return {"type": "ir.actions.act_window_close"}
