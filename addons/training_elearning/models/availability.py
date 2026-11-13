"""An explicit closure changes availability, never an existing acquisition."""

from uuid import uuid4
from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

PROTECTED = {"learning_withdrawn_at", "learning_availability_event", "learning_availability_log"}


class Course(models.Model):
    _inherit = "slide.channel"  # pylint: disable=consider-merging-classes-inherited

    def write(self, values):
        if values.get("active") is False and self.filtered("training_course_id")._learning_frozen():
            raise ValidationError(
                self.env._("Stop commercialization on the product; close engaged activities with an explicit reason.")
            )
        return super().write(values)


class Slide(models.Model):
    _inherit = "slide.slide"  # pylint: disable=consider-merging-classes-inherited
    learning_withdrawn_at = fields.Datetime(readonly=True, copy=False)
    learning_availability_event = fields.Char(readonly=True, copy=False)
    learning_availability_log = fields.Json(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if any(PROTECTED & values.keys() for values in vals_list) or any(
            "default_" + name in self.env.context for name in PROTECTED
        ):
            raise AccessError(self.env._("Activity closures are traced by the server."))
        return super().create(vals_list)

    def write(self, values):
        if PROTECTED & values.keys():
            raise AccessError(self.env._("Use the motivated activity availability action."))
        if values.get("active") is False and self.sudo().channel_id.filtered("training_course_id")._learning_frozen():
            raise ValidationError(
                self.env._("Close an engaged activity with a reason instead of archiving it directly.")
            )
        return super().write(values)

    @api.private
    def _learning_available(self):
        self.ensure_one()
        return bool(self.active and self.is_published and not self.learning_withdrawn_at)

    @api.private
    def _learning_supported(self):
        return not self.learning_withdrawn_at and super()._learning_supported()

    @api.private
    def _learning_on_withdraw(self, reason):
        pass  # Evaluated adapters preserve interrupted evidence without a failure.

    def action_learning_availability(self):
        self.ensure_one()
        self.channel_id._learning_staff(manager=True)
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.availability",
            "view_mode": "form",
            "target": "new",
            "context": {"default_slide_id": self.id},
        }

    def action_learning_change_availability(self, reason=None, reopen=False):
        self.ensure_one()
        self.channel_id._learning_staff(manager=True)
        self.channel_id._learning_lock_graph()
        self.lock_for_update()
        self.invalidate_recordset()
        if (
            not isinstance(reason, str)
            or not reason.strip()
            or type(reopen) is not bool
            or not self.channel_id.training_course_id
            or not self.active
            or not self.is_published
            or self.channel_id.learning_state != "published"
        ):
            raise ValidationError(
                self.env._("Choose a published course activity and provide an availability decision reason.")
            )
        if bool(self.learning_withdrawn_at) != reopen:
            return True  # Replays never create a new event or a second notification.
        event = str(uuid4())
        log = list(self.learning_availability_log or [])
        log.append(
            {
                "actor": self.env.uid,
                "at": fields.Datetime.to_string(fields.Datetime.now()),
                "event": event,
                "action": "reopen" if reopen else "withdraw",
                "reason": reason.strip(),
            }
        )
        with self.env.cr.savepoint():
            self._learning_store_version(
                {
                    "learning_withdrawn_at": False if reopen else fields.Datetime.now(),
                    "learning_availability_event": event,
                    "learning_availability_log": log,
                }
            )
            if reopen:
                if not self._learning_supported():
                    raise ValidationError(self.env._("Resolve the unavailable underlying resource before reopening."))
            else:
                self._learning_on_withdraw(reason.strip())
            members = (
                self.env["slide.channel.partner"]
                .sudo()
                .with_context(active_test=False)
                .search([("channel_id", "=", self.channel_id.id), ("learning_started_at", "!=", False)])
            )
            impacted = members.filtered(
                lambda member: any(item["id"] == self.id for item in member._learning_plan()["slides"])
            )
            for member in impacted:
                self.env["training.elearning.notice"]._queue(member, self, "reopen" if reopen else "withdrawal", event)
            impacted._learning_sync_progress()
            if not reopen and impacted:
                self.channel_id.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=self.env.uid,
                    summary=self.env._("Review affected learning obligations and contractual dates"),
                )
            self.channel_id.message_post(
                body=Markup("<p>%s</p>")
                % self.env._(
                    "Availability decision for %(activity)s: %(reason)s", activity=self.name, reason=reason.strip()
                ),
                subtype_xmlid="mail.mt_note",
            )
        return True
