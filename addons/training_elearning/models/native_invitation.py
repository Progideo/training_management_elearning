# pylint: disable=context-overridden  # Native account creation never inherits caller-supplied defaults.
"""A native account and deferred invitation, committed with its authorized grant."""

from contextvars import ContextVar
from odoo import api, models, Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import email_normalize
from .course import MANAGER

NATIVE_INVITATION = ContextVar("learning_native_invitation", default=None)


class Accounts(models.AbstractModel):
    _name = "training.elearning.account.service"
    _description = "Controlled Native Learning Invitation"

    @api.private
    def _prepare(self, partner, company):
        user = self.env.user
        if (
            not user.active
            or not user.has_group(MANAGER)
            or company not in self.env.companies
            or company not in user.company_ids
        ):
            raise AccessError(self.env._("Use an active learning coordinator of this operating company."))
        partner.ensure_one()
        partner.check_access("read")
        if partner.company_id and partner.company_id != company:
            raise AccessError(self.env._("Choose a beneficiary of this operating company."))
        partner.lock_for_update()
        users = partner.sudo().with_context(active_test=False).user_ids
        mails = self.env["mail.mail"].sudo().browse()
        if users:
            if len(users) != 1 or not users.active or users._is_public() or company not in users.company_ids:
                raise ValidationError(
                    self.env._("The coordination must resolve this beneficiary's native Odoo account.")
                )
            return users, mails
        email = email_normalize(partner.email)
        if not email or self.env["res.users"].sudo().with_context(active_test=False).search_count(
            [
                ("partner_id", "!=", partner.id),
                "|",
                ("login", "=ilike", email),
                ("partner_id.email_normalized", "=", email),
            ],
            limit=1,
        ):
            raise ValidationError(
                self.env._("The coordination must resolve this beneficiary's native Odoo invitation.")
            )
        # Limited delegation to the native wizard for this checked contact only;
        # it does not grant the coordinator global user-administration privileges.
        wizard = (
            self.env["portal.wizard"]
            .sudo()
            .with_company(company)
            .with_context({"allowed_company_ids": company.ids})
            .create({"partner_ids": [Command.set(partner.ids)]})
        )
        row = wizard.user_ids.filtered(lambda item: item.partner_id == partner)
        if len(row) != 1 or row.email_state != "ok" or row.user_id:
            raise ValidationError(
                self.env._("The coordination must resolve this beneficiary's native Odoo invitation.")
            )
        scope = {"partner": partner.id, "company": company.id, "actor": self.env.uid, "mails": []}
        token = NATIVE_INVITATION.set(scope)
        try:
            row.action_grant_access()
        except (AccessError, UserError) as error:
            raise ValidationError(self.env._("The coordination must finalize the native Odoo invitation.")) from error
        finally:
            NATIVE_INVITATION.reset(token)
        return row.sudo().user_id, mails.browse(scope["mails"])

    @api.private
    def _bind(self, source, user, mails):
        for mail in mails:
            notice = self.env["training.elearning.reminder"]._enqueue(
                "invitation", source, event=user.id, existing_mail=mail
            )
            if not notice or notice.mail_id != mail or notice.state != "queued":
                mail.sudo().write({"state": "cancel"})
                raise ValidationError(self.env._("The native invitation could not be bound to its authorized grant."))


class Template(models.Model):
    _inherit = "mail.template"

    def send_mail(self, res_id, force_send=False, raise_exception=False, email_values=None, email_layout_xmlid=False):
        scope = NATIVE_INVITATION.get()
        if not scope or self != self.env.ref("auth_signup.portal_set_password_email"):
            return super().send_mail(
                res_id,
                force_send=force_send,
                raise_exception=raise_exception,
                email_values=email_values,
                email_layout_xmlid=email_layout_xmlid,
            )
        user = self.env["res.users"].sudo().browse(res_id).exists()
        if (
            self.env.uid != scope["actor"]
            or user.partner_id.id != scope["partner"]
            or scope["company"] not in user.company_ids.ids
        ):
            raise AccessError(self.env._("Use only the checked beneficiary's native invitation."))
        values = dict(email_values or {})
        values.update(
            recipient_ids=[Command.set(user.partner_id.ids)],
            email_to=False,
            email_cc=False,
            attachment_ids=[Command.clear()],
            auto_delete=False,
        )
        mail_id = super().send_mail(
            res_id,
            force_send=False,
            raise_exception=raise_exception,
            email_values=values,
            email_layout_xmlid=email_layout_xmlid,
        )
        scope["mails"].append(mail_id)
        return mail_id


class Membership(models.Model):
    _inherit = "slide.channel.partner"

    def action_learning_activate(self, ends_at, user_id=None, reason=None):
        self.ensure_one()
        with self.env.cr.savepoint():
            self.channel_id._learning_staff(manager=True)
            self.channel_id.lock_for_update()
            self.lock_for_update()
            accounts = self.env["training.elearning.account.service"]
            mails = self.env["mail.mail"].browse()
            if not user_id:
                user, mails = accounts._prepare(self.partner_id, self.channel_id.learning_company_id)
                user_id = user.id
            result = super().action_learning_activate(ends_at, user_id, reason)
            accounts._bind(self, self.learning_user_id, mails)
            return result


class Activation(models.Model):
    _inherit = "training.elearning.path.activation"

    @api.private
    def _activate(self, path, partner, plan, access_months, start_months, reason, source=None):
        with self.env.cr.savepoint():
            path._staff(manager=True)
            accounts = self.env["training.elearning.account.service"]
            user, mails = accounts._prepare(partner, path.company_id)
            result = super()._activate(path, partner, plan, access_months, start_months, reason, source=source)
            accounts._bind(result, user, mails)
            return result
