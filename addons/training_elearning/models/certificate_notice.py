# pylint: disable=super-method-mismatch,method-required-super,context-overridden
"""Native, attachment-free holder notifications with a live check before transport."""

from odoo import api, fields, models, Command
from odoo.exceptions import AccessError
from .certificate import PEDAGOGY, staff


class Notice(models.Model):
    _name = "training.elearning.certificate.notice"
    _description = "Private Learning Certificate Notification"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "kind"
    certificate_id = fields.Many2one(
        "training.elearning.certificate", required=True, readonly=True, ondelete="restrict"
    )
    company_id = fields.Many2one(related="certificate_id.company_id")
    kind = fields.Selection(
        [("issued", "Délivrance"), ("withdrawn", "Retrait"), ("replaced", "Remplacement")], required=True, readonly=True
    )
    state = fields.Selection(
        [
            ("pending", "À préparer"),
            ("queued", "En file d’envoi"),
            ("sent", "Envoyé"),
            ("exception", "Incident d’envoi"),
            ("cancelled", "Annulé"),
        ],
        default="pending",
        readonly=True,
    )
    mail_id = fields.Many2one("mail.mail", readonly=True, ondelete="set null")
    sent_at = fields.Datetime(readonly=True)
    incident_activity_id = fields.Many2one("mail.activity", readonly=True, ondelete="set null")
    _one_event = models.Constraint("UNIQUE(certificate_id,kind)", "This certificate notification is already recorded.")

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Certificate notifications originate in checked document events."))

    def write(self, values):
        raise AccessError(self.env._("Keep certificate notification evidence."))

    @api.ondelete(at_uninstall=False)
    def _keep_notice(self):
        raise AccessError(self.env._("Keep certificate notification history."))

    @api.private
    def _store(self, values):
        return super(Notice, self.sudo()).write(values)

    @api.private
    def _allowed(self):
        self.ensure_one()
        document = self.sudo().certificate_id
        user = document.user_id
        source = document.membership_id or document.registration_id
        source_user = source.learning_user_id if document.membership_id else source.user_id
        return bool(
            user.active
            and not user._is_public()
            and document.company_id in user.company_ids
            and user.partner_id == source.partner_id
            and source_user == user
        )

    @api.private
    def _queue(self, document, kind):
        notice = self.sudo().search([("certificate_id", "=", document.id), ("kind", "=", kind)], limit=1)
        if not notice:
            notice = super(Notice, self.sudo().with_context({})).create({"certificate_id": document.id, "kind": kind})
        notice._process()
        return notice

    @api.private
    def _incident(self):
        user = self.certificate_id.issued_by
        if not user.active or not user.has_group(PEDAGOGY) or self.company_id not in user.company_ids:
            user = (
                self.env["res.users"]
                .sudo()
                .search([("active", "=", True), ("company_ids", "in", self.company_id.ids)])
                .filtered(lambda candidate: candidate.has_group(PEDAGOGY))[:1]
            )
        if user and not self.incident_activity_id:
            activity = self.sudo().activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=self.env._("Resolve the certificate notification incident"),
            )
            self._store({"incident_activity_id": activity.id})

    @api.private
    def _process(self):
        for notice in self:
            notice.lock_for_update()
            notice.invalidate_recordset()
            if notice.state != "pending":
                continue
            if not notice._allowed():
                notice._store({"state": "cancelled"})
                continue
            try:
                with self.env.cr.savepoint():
                    mail = (
                        self.env.ref("training_elearning.certificate_notice_template")
                        .sudo()
                        .send_mail(
                            notice.id,
                            force_send=False,
                            email_values={
                                "recipient_ids": [Command.set(notice.certificate_id.user_id.partner_id.ids)],
                                "email_to": False,
                                "email_cc": False,
                                "attachment_ids": [Command.clear()],
                            },
                        )
                    )
                    if not mail:
                        raise AccessError(self.env._("The native certificate notification was not queued."))
                    notice._store({"state": "queued", "mail_id": mail})
            except Exception:
                notice._store({"state": "exception"})
                notice._incident()

    @api.private
    def _sync(self):
        for notice in self.filtered(lambda row: row.state == "queued"):
            if notice.mail_id.state == "sent":
                notice._store({"state": "sent", "sent_at": fields.Datetime.now()})
                if notice.incident_activity_id:
                    notice.incident_activity_id.sudo().action_feedback(
                        feedback=self.env._("Certificate notification delivery is confirmed.")
                    )
                    notice._store({"incident_activity_id": False})
            elif not notice.mail_id or notice.mail_id.state in ("exception", "cancel"):
                notice._store({"state": "exception"})
                notice._incident()

    def action_retry(self):
        for notice in self:
            staff(notice.certificate_id)
            notice.lock_for_update()
            notice.invalidate_recordset()
            if notice.state == "exception":
                if notice.mail_id:
                    notice.mail_id.sudo().write({"state": "outgoing", "failure_reason": False, "failure_type": False})
                    notice._store({"state": "queued"})
                else:
                    notice._store({"state": "pending"})
                    notice._process()
        return True

    @api.model
    def _cron_certificate_notifications(self):
        notices = self.sudo().search([("state", "in", ("pending", "queued"))], limit=100)
        notices._process()
        notices._sync()


class Certificate(models.Model):
    _inherit = "training.elearning.certificate"

    @api.private
    def _notify(self, kind):
        return self.env["training.elearning.certificate.notice"]._queue(self, kind)


class Mail(models.Model):
    _inherit = "mail.mail"

    @api.private
    def _learning_delivery_allowed(self):
        if not super()._learning_delivery_allowed():
            return False
        notices = self.env["training.elearning.certificate.notice"].sudo().search([("mail_id", "=", self.id)])
        for notice in notices:
            if (
                not notice._allowed()
                or self.sudo().recipient_ids != notice.certificate_id.user_id.partner_id
                or self.sudo().email_to
                or self.sudo().email_cc
                or self.sudo().attachment_ids
            ):
                notice._store({"state": "cancelled"})
                return False
        return True
