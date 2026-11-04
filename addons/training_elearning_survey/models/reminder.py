"""A revised autonomous result is announced without exposing its detailed correction."""

from odoo import api, fields, models


class Reminder(models.Model):
    _inherit = "training.elearning.reminder"
    kind = fields.Selection(
        selection_add=[("exam_revision", "Exam Result Revised")], ondelete={"exam_revision": "cascade"}
    )
    result_revision_id = fields.Many2one("training.exam.revision", readonly=True, ondelete="restrict")

    @api.private
    def _source_field(self, source):
        return "result_revision_id" if source._name == "training.exam.revision" else super()._source_field(source)

    @api.private
    def _target(self):
        if self.kind != "exam_revision":
            return super()._target()
        revision = self.sudo().result_revision_id
        attempt = revision.attempt_id
        member = attempt.learning_membership_id
        if (
            not member
            or not revision
            or attempt.mock_context_key != "slide.channel.partner:%s" % member.id
            or member.learning_user_id.partner_id != member.partner_id
        ):
            return False
        return {
            "user": member.learning_user_id,
            "company": revision.company_id,
            "deadline": False,
            "url": "/my/learning/%s/history" % member.id,
        }
