"""Recheck native chatter/activity recipients for learning records before SMTP."""

from odoo import api, models
from odoo.exceptions import AccessError


class Mail(models.Model):
    _inherit = "mail.mail"

    @api.private
    def _learning_delivery_allowed(self):
        if not super()._learning_delivery_allowed():
            return False
        # Typed notices deliberately expose a private projection to recipients
        # who have no raw access to the internal delivery-evidence record.
        for model in (
            "training.elearning.notice",
            "training.elearning.path.notice",
            "training.elearning.review.notice",
            "training.elearning.certificate.notice",
            "training.elearning.reminder",
        ):
            if self.env[model].sudo().search_count([("mail_id", "=", self.id)], limit=1):
                return True
        mail = self.sudo()
        model = mail.model or ""
        # These pre-existing library/TM adapter models keep their own contracts.
        shared = {
            "training.elearning.resource",
            "training.elearning.version",
            "training.elearning.file",
            "training.elearning.lease",
            "training.elearning.assignment",
            "training.elearning.usage",
            "training.elearning.attempt",
            "training.elearning.event",
            "training.elearning.invalidation",
        }
        scoped = model.startswith("training.elearning.") and model not in shared
        if model in ("slide.channel", "slide.channel.partner", "survey.user_input"):
            if model not in self.env:
                return False
            record = self.env[model].sudo().browse(mail.res_id).exists()
            if model == "slide.channel":
                scoped = bool(record.training_course_id)
            elif model == "slide.channel.partner":
                scoped = bool(record.channel_id.training_course_id)
            elif "learning_membership_id" in record._fields:
                scoped = bool(record.learning_membership_id)
        if not scoped:
            return True
        if (
            model not in self.env
            or not mail.res_id
            or mail.email_to
            or mail.email_cc
            or mail.attachment_ids
            or not mail.recipient_ids
        ):
            return False
        record = self.env[model].sudo().browse(mail.res_id).exists()
        if not record:
            return False
        company = (
            record.company_id
            if "company_id" in record._fields
            else record.learning_company_id
            if "learning_company_id" in record._fields
            else record.channel_id.learning_company_id
            if model == "slide.channel.partner"
            else False
        )
        if not company:
            return False
        for partner in mail.recipient_ids:
            users = partner.with_context(active_test=False).user_ids.filtered(
                lambda user: user.active and not user._is_public() and company in user.company_ids
            )
            if not users:
                return False
            allowed = False
            for user in users:
                # Check current roles explicitly as well as native record rules;
                # an ACL result cached earlier in this transaction is insufficient.
                if model.startswith("training.elearning.sale."):
                    live_role = user.has_group("training_elearning_sale.group_learning_sales_manager")
                else:
                    live_role = (
                        user.has_group("training_elearning.group_elearning_pedagogy_manager")
                        or user.has_group("training_elearning.group_elearning_reviewer")
                        or (
                            model in ("slide.channel", "training.elearning.practical", "training.elearning.path")
                            and user.has_group("training_elearning.group_elearning_author")
                        )
                    )
                if not live_role:
                    continue
                try:
                    record.with_env(
                        self.env(user=user.id, su=False, context={"allowed_company_ids": company.ids})
                    ).check_access("read")
                except AccessError:
                    continue
                allowed = True
                break
            if not allowed:
                return False
        return True
