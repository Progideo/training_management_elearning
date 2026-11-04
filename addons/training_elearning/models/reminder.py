# pylint: disable=method-required-super,super-method-mismatch,context-overridden
"""Typed native notifications: future reminders, stable event keys and live SMTP authorization."""

from datetime import timedelta, UTC
from contextvars import ContextVar
from psycopg2.errors import UniqueViolation
from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, ValidationError
from .human_practical import PEDAGOGY, valid_reviewer

SUPPRESS_ACTIVATION = ContextVar("learning_notification_activation", default=False)
POLICY = {
    "learning_notice_long_days",
    "learning_notice_short_days",
    "learning_notice_revision_days",
    "learning_notice_correction_days",
}
KINDS = [
    ("activation", "Learner Access Activated"),
    ("invalidation", "Acquisition Decision"),
    ("course_end", "Course Access Ending"),
    ("path_start", "Curriculum Start Period Ending"),
    ("revision_end", "Practical Revision Ending"),
    ("review_due", "Practical Review Due"),
    ("review_late", "Practical Review Overdue"),
]


class Company(models.Model):
    _inherit = "res.company"
    learning_notice_long_days = fields.Integer(string="Premier rappel des délais longs (jours)", default=30)
    learning_notice_short_days = fields.Integer(string="Second rappel des délais longs (jours)", default=7)
    learning_notice_revision_days = fields.Integer(string="Rappel de révision de TP (jours)", default=3)
    learning_notice_correction_days = fields.Integer(string="Rappel de correction (jours ouvrés)", default=1)

    def write(self, values):
        if POLICY & values.keys() and (not self.env.user.active or not self.env.user.has_group("base.group_system")):
            raise AccessError(self.env._("Only an active administrator configures learning reminders."))
        return super().write(values)

    @api.constrains(*sorted(POLICY))
    def _check_notice_policy(self):
        if any(not 0 <= company[name] <= 365 for company in self for name in POLICY):
            raise ValidationError(self.env._("Set reminder offsets between zero (disabled) and 365 days."))


class Reminder(models.Model):
    _name = "training.elearning.reminder"
    _description = "Private Scoped Learning Notification"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "kind"
    _order = "due_at,id"
    kind = fields.Selection(KINDS, required=True, readonly=True)
    event_key = fields.Char(required=True, readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True, ondelete="restrict", index=True)
    user_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    partner_id = fields.Many2one("res.partner", required=True, readonly=True, ondelete="restrict")
    membership_id = fields.Many2one("slide.channel.partner", readonly=True, ondelete="restrict", index=True)
    activation_id = fields.Many2one("training.elearning.path.activation", readonly=True, ondelete="restrict")
    queue_id = fields.Many2one("training.elearning.review.queue", readonly=True, ondelete="restrict")
    invalidation_id = fields.Many2one("training.elearning.acquisition.invalidation", readonly=True, ondelete="restrict")
    deadline = fields.Datetime(readonly=True)
    due_at = fields.Datetime(required=True, readonly=True, index=True)
    offset_days = fields.Integer(readonly=True)
    source_event = fields.Char(readonly=True)
    state = fields.Selection(
        [
            ("pending", "Scheduled"),
            ("queued", "Queued"),
            ("sent", "Sent"),
            ("exception", "Delivery Incident"),
            ("cancelled", "Cancelled"),
        ],
        default="pending",
        required=True,
        readonly=True,
        index=True,
    )
    mail_id = fields.Many2one("mail.mail", readonly=True, ondelete="set null")
    sent_at = fields.Datetime(readonly=True)
    incident_activity_id = fields.Many2one("mail.activity", readonly=True, ondelete="set null")
    _one_event = models.Constraint("UNIQUE(event_key)", "This learning event is already scheduled.")

    @api.model_create_multi
    def create(self, values):
        raise AccessError(self.env._("Notifications originate in checked learning events."))

    def write(self, values):
        raise AccessError(self.env._("Keep learning notification evidence."))

    @api.ondelete(at_uninstall=False)
    def _keep_events(self):
        raise AccessError(self.env._("Keep learning notification history."))

    @api.private
    def _store(self, values):
        return super(Reminder, self.sudo()).write(values)

    @api.private
    def _coordinators(self, company):
        return (
            self.env["res.users"]
            .sudo()
            .search([("active", "=", True), ("company_ids", "in", company.ids)])
            .filtered(lambda user: user.has_group(PEDAGOGY))
        )

    @api.private
    def _target(self):
        """Resolve a typed source afresh; never trust frozen recipient details alone."""
        self.ensure_one()
        item = self.sudo()
        member = item.membership_id
        if item.kind == "invalidation":
            event = item.invalidation_id
            if not event or event.membership_id != member or event.request_key != item.source_event:
                return False
        if item.kind in ("activation", "invalidation", "course_end"):
            user = member.learning_user_id
            if not member.learning_started_at or user.partner_id != member.partner_id:
                return False
            company = member.channel_id.learning_company_id
            if item.kind != "invalidation" and (
                not member.active
                or member.learning_state != "active"
                or not member.channel_id.active
                or member.channel_id.learning_state != "published"
            ):
                return False
            if item.kind in ("course_end", "activation") and member.learning_ends_at <= fields.Datetime.now():
                return False
            if item.kind == "activation" and item.source_event != str(len(member.learning_access_log or [])):
                return False
            return {
                "user": user,
                "company": company,
                "deadline": member.learning_ends_at if item.kind != "invalidation" else False,
                "url": "/my/learning/%s/history" % member.id
                if item.kind == "invalidation"
                else "/my/learning/%s" % member.id,
            }
        if item.kind == "path_start":
            activation = item.activation_id
            if (
                not activation._authorized()
                or activation.start_paused
                or activation.starts_until <= fields.Datetime.now()
                or not activation.item_ids.filtered(lambda row: not row.activated_at)
            ):
                return False
            return {
                "user": activation.registration_id.user_id,
                "company": activation.company_id,
                "deadline": activation.starts_until,
                "url": "/my/learning-paths/%s" % activation.registration_id.id,
            }
        if item.kind in ("revision_end", "review_due", "review_late"):
            queue = item.queue_id
            if queue.membership_id != member:
                return False
            if item.kind == "revision_end":
                if not queue._revision_open():
                    return False
                return {
                    "user": member.learning_user_id,
                    "company": queue.company_id,
                    "deadline": queue.revision_until,
                    "url": "/my/learning-submissions/%s" % queue.review_id.submission_id.id,
                }
            if queue.state != "pending" or not valid_reviewer(
                queue.reviewer_id, queue.company_id, member.learning_user_id
            ):
                return False
            if item.kind == "review_late":
                user = item.user_id
                if user not in item._coordinators(queue.company_id):
                    return False
            else:
                user = queue.reviewer_id
            return {
                "user": user,
                "company": queue.company_id,
                "deadline": queue.due_at,
                "url": "/odoo",
            }
        return False

    @api.private
    def _offsets(self):
        company = self.sudo().company_id
        if self.kind in ("course_end", "path_start"):
            return {company.learning_notice_long_days, company.learning_notice_short_days} - {0}
        if self.kind == "revision_end":
            return {company.learning_notice_revision_days} - {0}
        if self.kind == "review_due":
            return {company.learning_notice_correction_days} - {0}
        return {0}

    @api.private
    def _allowed(self):
        target = self._target()
        if self.kind == "review_due" and self.deadline <= fields.Datetime.now():
            return False
        if not target:
            return False
        user = target["user"]
        return bool(
            user == self.user_id
            and user.active
            and not user._is_public()
            and user.partner_id == self.partner_id
            and target["company"] == self.company_id
            and self.company_id in user.company_ids
            and target["deadline"] == self.deadline
            and self.offset_days in self._offsets()
        )

    @api.private
    def _source_field(self, source):
        return {
            "slide.channel.partner": "membership_id",
            "training.elearning.path.activation": "activation_id",
            "training.elearning.review.queue": "queue_id",
            "training.elearning.acquisition.invalidation": "invalidation_id",
        }.get(source._name)

    @api.private
    def _enqueue(self, kind, source, *, offset=0, event=None, recipient=None):
        """Only private checked hooks/scanners call this factory; no caller defaults survive."""
        field = self._source_field(source)
        if not field:
            return False
        values = {"kind": kind, field: source.id, "offset_days": offset, "source_event": str(event or "")}
        if source._name in ("training.elearning.review.queue", "training.elearning.acquisition.invalidation"):
            values["membership_id"] = source.sudo().membership_id.id
        if recipient:
            values["user_id"] = recipient.id
        draft = self.sudo().new(values)
        target = draft._target()
        if not target:
            return False
        deadline = target["deadline"]
        now = fields.Datetime.now()
        due = deadline - timedelta(days=offset) if offset else now
        if kind == "review_late":
            due = deadline
        if offset and kind == "review_due":
            queue = source.sudo()
            plan = next(row for row in queue.membership_id._learning_plan()["slides"] if row["id"] == queue.slide_id.id)
            calendar = self.env["resource.calendar"].sudo().browse(plan["review_calendar"])
            due = (
                calendar.plan_hours(
                    -offset * calendar.hours_per_day,
                    deadline.replace(tzinfo=UTC),
                    compute_leaves=True,
                    resource=calendar.learning_review_resource_id,
                )
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
        # No catch-up: a new source or new policy cannot create an already-due reminder.
        if (offset or kind == "review_late") and due <= now:
            return False
        user, company = target["user"], target["company"]
        key = "%s:%s:%s:%s:%s:%s:%s" % (
            kind,
            source._name,
            source.id,
            user.id,
            fields.Datetime.to_string(deadline),
            offset,
            event or "",
        )
        old = self.sudo().search([("event_key", "=", key)], limit=1)
        if old:
            return old
        values.update(
            company_id=company.id,
            user_id=user.id,
            partner_id=user.partner_id.id,
            deadline=deadline,
            due_at=due,
            event_key=key,
        )
        try:
            with self.env.cr.savepoint():
                notice = super(Reminder, self.sudo().with_context({})).create(values)
        except UniqueViolation:
            # Another worker already owns this event. Under repeatable read its
            # row can remain invisible until the next transaction; preserving
            # the business action is preferable to preparing a duplicate mail.
            return self.sudo().search([("event_key", "=", key)], limit=1)
        if not notice._allowed():
            notice._store({"state": "cancelled"})
        elif not offset:
            notice._process()
        return notice

    @api.private
    def _incident(self):
        for notice in self:
            if notice.incident_activity_id:
                continue
            coordinator = notice._coordinators(notice.company_id)[:1]
            if coordinator:
                task = notice.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=coordinator.id,
                    summary=self.env._("Resolve the scoped learning notification incident"),
                )
                notice._store({"incident_activity_id": task.id})

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
            if notice.due_at > fields.Datetime.now():
                continue
            try:
                with self.env.cr.savepoint():
                    mail = (
                        self.env.ref("training_elearning.scoped_reminder_template")
                        .sudo()
                        .send_mail(
                            notice.id,
                            force_send=False,
                            email_values={
                                "recipient_ids": [Command.set(notice.partner_id.ids)],
                                "email_to": False,
                                "email_cc": False,
                                "attachment_ids": [Command.clear()],
                            },
                        )
                    )
                    if not mail:
                        raise ValidationError(self.env._("The scoped notification was not queued."))
                    notice._store({"mail_id": mail, "state": "queued"})
            except Exception:
                notice._store({"state": "exception"})
                notice._incident()

    @api.private
    def _sync(self):
        for notice in self.filtered(lambda row: row.state in ("queued", "sent")):
            mail = notice.mail_id
            if not mail or mail.state in ("exception", "cancel"):
                notice._store({"state": "exception"})
                notice._incident()
            elif mail.state == "sent" and notice.state != "sent":
                notice._store({"state": "sent", "sent_at": fields.Datetime.now()})

    def action_retry(self):
        for notice in self:
            if (
                not self.env.user.active
                or not self.env.user.has_group(PEDAGOGY)
                or notice.company_id not in self.env.companies
            ):
                raise AccessError(self.env._("Use the pedagogical coordinator of this operating company."))
            notice.lock_for_update()
            notice.invalidate_recordset()
            if notice.state != "exception":
                continue
            if not notice._allowed():
                notice._store({"state": "cancelled"})
            elif notice.mail_id:
                notice.mail_id.sudo().write({"state": "outgoing", "failure_type": False, "failure_reason": False})
                notice._store({"state": "queued"})
            else:
                notice._store({"state": "pending"})
                notice._process()
        return True

    @api.private
    def _scan_records(self, model, domain):
        params = self.env["ir.config_parameter"].sudo()
        key = "training_elearning.reminder_cursor." + model
        cursor = int(params.get_str(key, "0"))
        rows = self.env[model].sudo().search(domain + [("id", ">", cursor)], order="id", limit=250)
        params.set_str(key, str(rows[-1].id if len(rows) == 250 else 0))
        return rows

    @api.private
    def _scan_sources(self):
        now = fields.Datetime.now()
        for member in self._scan_records(
            "slide.channel.partner", [("learning_state", "=", "active"), ("learning_ends_at", ">", now)]
        ):
            for days in {
                member.channel_id.learning_company_id.learning_notice_long_days,
                member.channel_id.learning_company_id.learning_notice_short_days,
            } - {0}:
                self._enqueue("course_end", member, offset=days)
        for activation in self._scan_records(
            "training.elearning.path.activation", [("starts_until", ">", now), ("start_paused", "=", False)]
        ):
            for days in {
                activation.company_id.learning_notice_long_days,
                activation.company_id.learning_notice_short_days,
            } - {0}:
                self._enqueue("path_start", activation, offset=days)
        for queue in self._scan_records("training.elearning.review.queue", [("state", "in", ("pending", "revision"))]):
            self._schedule_queue(queue)

    @api.private
    def _schedule_queue(self, queue):
        company = queue.company_id
        if queue.state == "revision" and company.learning_notice_revision_days:
            self._enqueue("revision_end", queue, offset=company.learning_notice_revision_days)
        elif queue.state == "pending":
            for user in self._coordinators(company):
                self._enqueue(
                    "review_late", queue, event=fields.Datetime.to_string(queue.first_received_at), recipient=user
                )
            if company.learning_notice_correction_days:
                self._enqueue("review_due", queue, offset=company.learning_notice_correction_days)

    @api.model
    def _cron_scoped_notifications(self):
        self._scan_sources()
        params = self.env["ir.config_parameter"].sudo()
        cursor = int(params.get_str("training_elearning.notice_sync_cursor", "0"))
        rows = self.sudo().search(
            [("state", "in", ("pending", "queued", "sent")), ("id", ">", cursor)], order="id", limit=500
        )
        params.set_str("training_elearning.notice_sync_cursor", str(rows[-1].id if len(rows) == 500 else 0))
        rows.filtered(lambda row: row.state == "pending")._process()
        rows._sync()


class Mail(models.Model):
    _inherit = "mail.mail"

    @api.private
    def _learning_delivery_allowed(self):
        if not super()._learning_delivery_allowed():
            return False
        notices = self.env["training.elearning.reminder"].sudo().search([("mail_id", "=", self.id)])
        for notice in notices:
            mail = self.sudo()
            if (
                not notice._allowed()
                or mail.recipient_ids != notice.partner_id
                or mail.email_to
                or mail.email_cc
                or mail.attachment_ids
            ):
                notice._store({"state": "cancelled"})
                return False
        return True

    def _send(
        self,
        auto_commit=False,
        raise_exception=False,
        smtp_session=None,
        alias_domain_id=False,
        mail_server=False,
        post_send_callback=None,
    ):
        result = super()._send(
            auto_commit=auto_commit,
            raise_exception=raise_exception,
            smtp_session=smtp_session,
            alias_domain_id=alias_domain_id,
            mail_server=mail_server,
            post_send_callback=post_send_callback,
        )
        self.env["training.elearning.reminder"].sudo().search([("mail_id", "in", self.ids)])._sync()
        return result
