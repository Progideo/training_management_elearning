# pylint: disable=super-method-mismatch,context-overridden,method-required-super
"""Contractual start windows produce native course grants, never a parallel curriculum access right."""

from contextvars import ContextVar
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError, LockError
from .course import MANAGER

_STARTING = ContextVar("learning_paths_starting", default=False)


class Activation(models.Model):
    _name = "training.elearning.path.activation"
    _description = "Authorized Curriculum Course Start Window"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "registration_id"
    registration_id = fields.Many2one(
        "training.elearning.path.registration",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    company_id = fields.Many2one(related="registration_id.company_id")
    activated_at = fields.Datetime(required=True, readonly=True)
    starts_until = fields.Datetime(required=True, readonly=True)
    access_months = fields.Integer(required=True, readonly=True)
    plan = fields.Json(required=True, readonly=True)
    reason = fields.Text(required=True, readonly=True)
    adjustment_log = fields.Json(readonly=True)
    item_ids = fields.One2many("training.elearning.path.item", "activation_id", readonly=True)
    start_paused = fields.Boolean(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Activate a curriculum through its checked authorization."))

    def write(self, values):
        raise AccessError(self.env._("Use a motivated curriculum start-window adjustment."))

    @api.ondelete(at_uninstall=False)
    def _keep_activation(self):
        raise AccessError(self.env._("Keep contractual curriculum activation history."))

    @api.private
    def _store(self, values):
        return super(Activation, self.sudo()).write(values)

    @api.private
    def _staff(self):
        self.registration_id.path_id._staff(manager=True)
        self.check_access("read")

    @api.private
    def _coordinator_group(self):
        return MANAGER

    @api.private
    def _coordinator(self):
        self.ensure_one()
        group = self._coordinator_group()
        candidates = (
            self.env["res.users"].sudo().search([("active", "=", True), ("company_ids", "in", self.company_id.ids)])
        )
        candidates = candidates.filtered(lambda user: not user.share and user.has_group(group))
        return self.create_uid if self.create_uid in candidates else candidates[:1]

    @api.private
    def _check_source(self, registration, values):
        registration.path_id._staff(manager=True)
        if values:
            raise AccessError(self.env._("Choose a recognized curriculum authorization source."))

    @api.private
    def _bind_source(self):
        return True

    @api.private
    def _authorized(self):
        self.ensure_one()
        return bool(
            self.activated_at
            and self.registration_id.user_id.active
            and self.company_id in self.registration_id.user_id.company_ids
        )

    @api.private
    def _activate(self, path, partner, plan, access_months, start_months, reason, source=None):
        source = source or {}
        path._staff(manager=True)
        path.lock_for_update()
        if not (reason or "").strip() or access_months <= 0 or start_months <= 0 or plan.get("path") != path.id:
            raise ValidationError(
                self.env._("Provide an authorized curriculum, positive month durations and a reason.")
            )
        registration = self.env["training.elearning.path.registration"]._ensure_registration(
            path, partner, plan.get("composition")
        )
        registration.lock_for_update()
        self._check_source(registration, source)
        included = plan.get("included", [])
        if (
            not included
            or len(set(included)) != len(included)
            or not set(included) <= {item["course"] for item in registration.composition}
            or set(plan.get("plans", {})) != {str(course) for course in included}
        ):
            raise ValidationError(self.env._("Use the explicitly frozen curriculum course selection."))
        now = fields.Datetime.now()
        try:
            until = now + relativedelta(months=start_months)
            until + relativedelta(months=access_months)
        except (ValueError, OverflowError) as error:
            raise ValidationError(self.env._("Choose month durations representable by the native calendar.")) from error
        activation = super(Activation, self.sudo().with_context({})).create(
            {
                "registration_id": registration.id,
                "activated_at": now,
                "starts_until": until,
                "access_months": access_months,
                "plan": plan,
                "reason": reason.strip(),
                **source,
            }
        )
        activation._bind_source()
        for course in included:
            self.env["training.elearning.path.item"]._create_item(activation, course, plan["plans"][str(course)])
        activation.item_ids._start_ready()
        self.env["training.elearning.path.notice"]._queue(activation)
        for days in {
            activation.company_id.learning_notice_long_days,
            activation.company_id.learning_notice_short_days,
        } - {0}:
            self.env["training.elearning.reminder"]._enqueue("path_start", activation, offset=days)
        return activation

    def action_adjust(self):
        self.ensure_one()
        self._staff()
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.path.adjust",
            "view_mode": "form",
            "target": "new",
            "context": {"default_activation_id": self.id},
        }

    @api.private
    def _adjust(self, until, reason, *, paused=False):
        self._staff()
        self.registration_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        until = fields.Datetime.to_datetime(until)
        if not until or until < self.starts_until or not (reason or "").strip():
            raise ValidationError(self.env._("Explain the adjustment and keep or extend the existing start limit."))
        if until == self.starts_until and bool(paused) == self.start_paused:
            self.item_ids._start_ready()
            return True
        log = list(self.adjustment_log or [])
        log.append(
            {
                "actor": self.env.uid,
                "at": fields.Datetime.to_string(fields.Datetime.now()),
                "before": fields.Datetime.to_string(self.starts_until),
                "after": fields.Datetime.to_string(until),
                "paused": bool(paused),
                "reason": reason.strip(),
            }
        )
        self._store({"starts_until": until, "start_paused": bool(paused), "adjustment_log": log})
        self.item_ids._start_ready()
        return True


class Item(models.Model):
    _name = "training.elearning.path.item"
    _description = "Native Course Activation in One Curriculum Contract"
    _rec_name = "course_id"
    activation_id = fields.Many2one(
        "training.elearning.path.activation",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    registration_id = fields.Many2one(related="activation_id.registration_id")
    company_id = fields.Many2one(related="activation_id.company_id")
    course_id = fields.Many2one("slide.channel", required=True, readonly=True, ondelete="restrict")
    plan = fields.Json(required=True, readonly=True)
    membership_id = fields.Many2one("slide.channel.partner", readonly=True, ondelete="restrict")
    activated_at = fields.Datetime(readonly=True)
    access_started_at = fields.Datetime(readonly=True)
    access_ends_at = fields.Datetime(readonly=True)
    blocked_at = fields.Datetime(readonly=True)
    block_reason = fields.Text(readonly=True)
    incident_activity_id = fields.Many2one("mail.activity", readonly=True, ondelete="set null")
    _one_course = models.Constraint(
        "UNIQUE(activation_id, course_id)",
        "This course is already in this contractual activation.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Curriculum course activations are generated by checked contracts."))

    def write(self, values):
        raise AccessError(self.env._("Keep native course activation provenance."))

    @api.ondelete(at_uninstall=False)
    def _keep_item(self):
        raise AccessError(self.env._("Keep curriculum course activation history."))

    @api.private
    def _store(self, values):
        return super(Item, self.sudo()).write(values)

    @api.private
    def _create_item(self, activation, course_id, plan):
        course = self.env["slide.channel"].sudo().browse(course_id).exists()
        if not course or course.learning_company_id != activation.company_id:
            raise ValidationError(self.env._("Choose native course editions in this contractual company."))
        return super(Item, self.sudo().with_context({})).create(
            {
                "activation_id": activation.id,
                "course_id": course_id,
                "plan": plan,
            }
        )

    @api.private
    def _ready(self):
        self.ensure_one()
        return all(
            self.registration_id._member(course).learning_started_at
            and self.registration_id._member(course)._learning_progress()["complete"]
            for course in self.plan.get("courses", [])
        )

    @api.private
    def _grant_interval(self, member, now):
        return now, now + relativedelta(months=self.activation_id.access_months)

    @api.private
    def _start(self):
        self.ensure_one()
        item = self.sudo()
        context = item.activation_id
        registration = item.registration_id
        # Lock order matches course evidence operations: native course, native
        # membership, then derived curriculum rows. The registration serializes
        # this person's parallel curriculum activations.
        item.course_id.lock_for_update()
        registration.lock_for_update()
        context.lock_for_update()
        item.lock_for_update()
        item.invalidate_recordset()
        context.invalidate_recordset()
        now = fields.Datetime.now()
        if (
            item.activated_at
            or context.start_paused
            or now >= context.starts_until
            or not context._authorized()
            or not item._ready()
        ):
            return False
        actor = context._coordinator()
        if not actor:
            raise ValidationError(self.env._("An active curriculum coordinator in this company is required."))
        courses = item.course_id.with_user(actor).with_context({"allowed_company_ids": item.company_id.ids})
        courses._learning_check_contents()
        model = (
            self.env["slide.channel.partner"]
            .with_user(actor)
            .with_context({"allowed_company_ids": item.company_id.ids})
        )
        member = model.with_context(active_test=False).search(
            [
                ("channel_id", "=", item.course_id.id),
                ("partner_id", "=", registration.partner_id.id),
            ],
            limit=1,
        )
        if member.learning_started_at and member.learning_state in (
            "suspended",
            "revoked",
        ):
            raise ValidationError(self.env._("Resolve the existing suspended or revoked course access explicitly."))
        start, end = item._grant_interval(member, now)
        union_end = max(end, member.learning_ends_at) if member.learning_started_at else end
        member = member or model.create({"channel_id": item.course_id.id, "partner_id": registration.partner_id.id})
        item._store({"membership_id": member.id})
        # The existing typed curriculum notice owns this opening event.
        from .reminder import SUPPRESS_ACTIVATION

        token = SUPPRESS_ACTIVATION.set(True)
        try:
            member.action_learning_activate(
                union_end,
                registration.user_id.id,
                self.env._("Authorized curriculum course activation %s", item.id),
            )
        finally:
            SUPPRESS_ACTIVATION.reset(token)
        item._store(
            {
                "activated_at": now,
                "access_started_at": start,
                "access_ends_at": end,
                "blocked_at": False,
                "block_reason": False,
            }
        )
        self.env["training.elearning.path.notice"]._queue(context, item=item)
        return True

    @api.private
    def _start_ready(self):
        if _STARTING.get():
            return
        token = _STARTING.set(True)
        try:
            for _round in range(len(self) + 1):
                started = False
                for item in self.sudo().sorted("id"):
                    if item.activated_at or not item._ready():
                        continue
                    try:
                        with self.env.cr.savepoint():
                            started = bool(item._start()) or started
                    except LockError:
                        continue  # The original course evidence remains committed; the native cron can retry.
                    except (AccessError, ValidationError) as error:
                        item._store(
                            {
                                "blocked_at": fields.Datetime.now(),
                                "block_reason": str(error),
                            }
                        )
                        actor = item.activation_id._coordinator()
                        if actor and not item.incident_activity_id:
                            activity = item.activation_id.sudo().activity_schedule(
                                "mail.mail_activity_data_todo",
                                user_id=actor.id,
                                summary=self.env._("Resolve the curriculum course activation"),
                            )
                            item._store({"incident_activity_id": activity.id})
                if not started:
                    break
        finally:
            _STARTING.reset(token)

    @api.model
    def _cron_path_starts(self):
        items = self.sudo().search(
            [
                ("activated_at", "=", False),
                ("activation_id.starts_until", ">", fields.Datetime.now()),
                ("activation_id.start_paused", "=", False),
            ],
            limit=100,
        )
        items._start_ready()


class Membership(models.Model):
    _inherit = "slide.channel.partner"

    @api.private
    def _learning_plan_source(self):
        self.ensure_one()
        pending = (
            self.env["training.elearning.path.item"]
            .sudo()
            .search(
                [
                    ("membership_id", "=", self.id),
                    ("activated_at", "=", False),
                ],
                limit=2,
            )
        )
        if not pending:
            return super()._learning_plan_source()
        if len(pending) != 1:
            raise ValidationError(self.env._("Resolve ambiguous curriculum course activation provenance."))
        item = pending.with_env(self.env)
        item.activation_id._staff()
        if (
            item.course_id != self.channel_id
            or item.registration_id.partner_id != self.partner_id
            or not item.activation_id._authorized()
        ):
            raise AccessError(self.env._("Use the authorized course activation of this curriculum learner."))
        return item.sudo().plan

    @api.private
    def _learning_sync_progress(self):
        result = super()._learning_sync_progress()
        if not _STARTING.get():
            self.env["training.elearning.path.item"].sudo().search(
                [
                    ("registration_id.partner_id", "in", self.partner_id.ids),
                    ("activated_at", "=", False),
                    ("activation_id.starts_until", ">", fields.Datetime.now()),
                    ("activation_id.start_paused", "=", False),
                ]
            )._start_ready()
        return result
