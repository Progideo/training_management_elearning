"""Enterprise mail remains bounded to a current explicit mandate and its purchase."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class Company(models.Model):
    _inherit = "res.company"
    learning_notice_report_days = fields.Integer(string="Rappel de fin de consultation du bilan (jours)", default=7)
    learning_notice_since = fields.Datetime(default=fields.Datetime.now, readonly=True, copy=False)

    def write(self, values):
        if "learning_notice_since" in values:
            raise AccessError(self.env._("Keep the notification activation date."))
        if "learning_notice_report_days" in values and (
            not self.env.user.active or not self.env.user.has_group("base.group_system")
        ):
            raise AccessError(self.env._("Only an active administrator configures report reminders."))
        return super().write(values)

    @api.constrains("learning_notice_report_days")
    def _check_report_reminder_policy(self):
        if any(not 0 <= company.learning_notice_report_days <= 365 for company in self):
            raise ValidationError(self.env._("Set the report reminder between zero (disabled) and 365 days."))


class Reminder(models.Model):
    _inherit = "training.elearning.reminder"
    kind = fields.Selection(
        selection_add=[
            ("assignment_end", "Seat Assignment Ending"),
            ("report_ready", "Purchase Report Available"),
            ("report_end", "Purchase Report Consultation Ending"),
        ],
        ondelete={"assignment_end": "cascade", "report_ready": "cascade", "report_end": "cascade"},
    )
    mandate_id = fields.Many2one("training.elearning.sale.mandate", readonly=True, ondelete="restrict", index=True)

    @api.private
    def _source_field(self, source):
        return "mandate_id" if source._name == "training.elearning.sale.mandate" else super()._source_field(source)

    @api.private
    def _purchase_closure(self, mandate):
        seats = mandate.sudo().line_id.learning_allocation_ids.filtered("activated_at")
        closures = [seat._purchase_summary().get("closed_at") for seat in seats]
        return max(closures) if closures and all(closures) else False

    @api.private
    def _target(self):
        if self.kind not in ("assignment_end", "report_ready", "report_end"):
            return super()._target()
        item = self.sudo()
        mandate = item.mandate_id
        if not mandate:
            return False
        service = self.env["training.elearning.company.service"].with_user(mandate.user_id)
        try:
            service._mandate(mandate.id, assign=self.kind == "assignment_end")
        except AccessError:
            return False
        line = mandate.line_id
        if self.kind == "assignment_end":
            if len(line.learning_allocation_ids) >= line.product_uom_qty:
                return False
            deadline = line.learning_assign_until
        else:
            closure = item._purchase_closure(mandate)
            if self.kind == "report_ready" and (not closure or self.source_event != fields.Datetime.to_string(closure)):
                return False
            if self.kind == "report_end" and not closure:
                return False  # Pending correction must never announce a final closure.
            deadline = service._ends_at(mandate)
        return {
            "user": mandate.user_id,
            "company": mandate.company_id,
            "deadline": deadline,
            "url": "/my/learning-purchases/%s" % mandate.id,
        }

    @api.private
    def _offsets(self):
        if self.kind == "assignment_end":
            return {self.company_id.learning_notice_long_days, self.company_id.learning_notice_short_days} - {0}
        if self.kind == "report_end":
            return {self.company_id.learning_notice_report_days} - {0}
        return super()._offsets()

    @api.private
    def _scan_sources(self):
        result = super()._scan_sources()
        for mandate in self._scan_records(
            "training.elearning.sale.mandate", [("state", "=", "active"), ("valid_until", ">", fields.Datetime.now())]
        ):
            company = mandate.company_id
            for days in {company.learning_notice_long_days, company.learning_notice_short_days} - {0}:
                self._enqueue("assignment_end", mandate, offset=days)
            closure = self._purchase_closure(mandate)
            if closure and max(closure, mandate.granted_at) >= company.learning_notice_since:
                self._enqueue("report_ready", mandate, event=fields.Datetime.to_string(closure))
            if company.learning_notice_report_days:
                self._enqueue("report_end", mandate, offset=company.learning_notice_report_days)
        return result


class Mail(models.Model):
    _inherit = "mail.mail"

    @api.private
    def _learning_delivery_allowed(self):
        if not super()._learning_delivery_allowed():
            return False
        from odoo.tools import email_normalize

        for seat in (
            self.env["training.elearning.sale.allocation"].sudo().search([("notification_mail_id", "=", self.id)])
        ):
            member = seat.membership_id
            user = member.learning_user_id
            mail = self.sudo()
            if not (
                seat.activated_at
                and member.active
                and member.learning_state == "active"
                and member.learning_ends_at > fields.Datetime.now()
                and member.channel_id.active
                and member.channel_id.learning_state == "published"
                and user.active
                and user.partner_id == seat.partner_id
                and seat.company_id in user.company_ids
                and (
                    mail.recipient_ids == user.partner_id
                    or mail.email_to
                    and email_normalize(mail.email_to) == email_normalize(user.partner_id.email)
                )
            ):
                return False
            if (
                mail.email_cc
                or mail.attachment_ids
                or mail.recipient_ids
                and mail.recipient_ids != user.partner_id
                or mail.email_to
                and email_normalize(mail.email_to) != email_normalize(user.partner_id.email)
            ):
                return False
        return True
