"""An institution interruption preserves answers without a pass/fail consequence."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain


class Attempt(models.Model):
    _inherit = "survey.user_input"  # pylint: disable=consider-merging-classes-inherited
    learning_interrupted_at = fields.Datetime(readonly=True, copy=False)
    learning_interruption_reason = fields.Text(
        readonly=True, copy=False, groups="training_elearning_survey.group_learning_exam_reader"
    )

    def _read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        # Keep interrupted proof in the native history, but do not count it as
        # an ordinary pass/fail answer in native Survey aggregates.
        domain = list(Domain(domain) & Domain("learning_interrupted_at", "=", False))
        return super()._read_group(
            domain, groupby=groupby, aggregates=aggregates, having=having, offset=offset, limit=limit, order=order
        )

    @api.private
    def _learning_interrupt(self, at, reason):
        self.ensure_one()
        member = self.sudo().learning_membership_id
        if (
            not member
            or not member.learning_started_at
            or self.learning_slide_id.channel_id != member.channel_id
            or self.mock_context_key != "slide.channel.partner:%s" % member.id
        ):
            raise AccessError(self.env._("Choose an actual autonomous course attempt."))
        member.channel_id._learning_staff(manager=True)
        self.lock_for_update()
        self.invalidate_recordset()
        if self.state == "done":
            return False
        if self.deadline <= at:
            # It had already expired when the institution made its decision.
            self._training_finish()
            return False
        self._training_store(
            {"state": "done", "end_datetime": at, "learning_interrupted_at": at, "learning_interruption_reason": reason}
        )
        member._learning_sync_progress()
        return True


class Slide(models.Model):
    _inherit = "slide.slide"  # pylint: disable=consider-merging-classes-inherited

    @api.private
    def _learning_on_withdraw(self, reason):
        result = super()._learning_on_withdraw(reason)
        # Only this course activity's native inputs; no other offer or TM context.
        attempts = (
            self.env["survey.user_input"]
            .sudo()
            .search(
                [
                    ("learning_slide_id", "in", self.ids),
                    ("learning_membership_id.channel_id", "in", self.channel_id.ids),
                    ("state", "!=", "done"),
                ]
            )
        )
        for attempt in attempts:
            attempt._learning_interrupt(self.learning_withdrawn_at, reason)
        return result


class Service(models.AbstractModel):
    _inherit = "training.elearning.exam.service"

    @api.private
    def _result(self, attempt):
        answer = self._attempt(attempt.id)
        if answer.learning_interrupted_at:
            raise AccessError(
                self.env._("An institution-interrupted attempt has no pass/fail result or final correction.")
            )
        return super()._result(answer)


class Survey(models.Model):
    _inherit = "survey.survey"

    def write(self, values):
        if "active" in values and not values["active"]:
            self.check_access("write")
            shared = self.filtered("training_course_id")
            if shared:
                shared._mock_editor()
                obligations = (
                    self.env["training.elearning.exam.requirement"]
                    .sudo()
                    .search(
                        [
                            ("exam_id", "in", shared.ids),
                            ("membership_id.learning_started_at", "!=", False),
                        ]
                    )
                )
                if obligations.filtered(lambda row: not row.slide_id.learning_withdrawn_at):
                    raise ValidationError(
                        self.env._("Close each engaged course activity with a reason before archiving its shared exam.")
                    )
        return super().write(values)
