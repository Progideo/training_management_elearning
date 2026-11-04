# pylint: disable=context-overridden  # private factories strip all caller-provided defaults
"""A named seat links one native sale line to the existing unique membership."""

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import email_normalize
from .offer import require_manager

PROTECTED = {
    "assigned_by",
    "assigned_mandate_id",
    "membership_id",
    "activated_at",
    "access_started_at",
    "access_ends_at",
    "notification_mail_id",
    "notification_state",
    "path_activation_id",
    "assignment_activity_id",
    "report_course_ids",
}


class Allocation(models.Model):
    _name = "training.elearning.sale.allocation"
    _description = "Named Autonomous Sale Seat"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "partner_id"
    line_id = fields.Many2one("sale.order.line", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one(related="line_id.company_id", store=True)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", tracking=True)
    assigned_by = fields.Many2one("res.users", readonly=True, copy=False, ondelete="restrict")
    assigned_mandate_id = fields.Many2one(
        "training.elearning.sale.mandate",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )
    membership_id = fields.Many2one("slide.channel.partner", readonly=True, copy=False, ondelete="restrict")
    activated_at = fields.Datetime(readonly=True, copy=False)
    access_started_at = fields.Datetime(readonly=True, copy=False)
    access_ends_at = fields.Datetime(readonly=True, copy=False)
    assignment_activity_id = fields.Many2one("mail.activity", readonly=True, copy=False, ondelete="set null")
    notification_mail_id = fields.Many2one("mail.mail", readonly=True, copy=False, ondelete="set null")
    notification_state = fields.Selection([("queued", "Queued"), ("exception", "Exception")], readonly=True, copy=False)
    _one_named_seat = models.Constraint(
        "UNIQUE(line_id, partner_id)",
        "This beneficiary already has a seat on this line.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if any(PROTECTED & vals.keys() for vals in vals_list) or any(
            "default_" + k in self.env.context for k in PROTECTED
        ):
            raise AccessError(self.env._("Activate the named seat through its controlled action."))
        prepared = {}
        lines = self.env["sale.order.line"]
        for vals in vals_list:
            line = self.env["sale.order.line"].browse(vals.get("line_id") or self.env.context.get("default_line_id"))
            require_manager(line)
            partner = self.env["res.partner"].browse(
                vals.get("partner_id") or self.env.context.get("default_partner_id")
            )
            partner.check_access("read")
            if not partner or (partner.company_id and partner.company_id != line.company_id):
                raise AccessError(self.env._("Choose a beneficiary visible in this operating company."))
            line.lock_for_update()
            line.invalidate_recordset()
            if not line._learning_managed_lines() or line.state == "cancel":
                raise ValidationError(self.env._("Choose an autonomous quotation or confirmed sale line."))
            used = self.sudo().search_count([("line_id", "=", line.id)])
            # Count earlier rows of this batch as well as committed allocations.
            used += prepared.get(line.id, 0)
            prepared[line.id] = prepared.get(line.id, 0) + 1
            if used >= line.product_uom_qty:
                raise ValidationError(self.env._("All seats on this sale line are already allocated."))
            if line.learning_assign_until and fields.Datetime.now() >= line.learning_assign_until:
                raise ValidationError(self.env._("The seat assignment period has ended."))
            lines |= line
        lines._learning_touch_allocations()
        return super().create(vals_list)

    def write(self, vals):
        require_manager(self)
        self.line_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        if PROTECTED & vals.keys() or "line_id" in vals or ("partner_id" in vals and self.activated_at):
            raise AccessError(self.env._("Keep activated seat identities and commercial evidence."))
        return super().write(vals)

    @api.private
    def _store(self, vals):
        return super(Allocation, self).write(vals)  # pylint: disable=super-method-mismatch  # checked private transitions

    def action_learning_prepare_portal(self):
        self.ensure_one()
        require_manager(self)
        # The standard wizard resolves email ambiguity and sends the native invitation.
        wizard = self.env["portal.wizard"].with_context({}).create({"partner_ids": [Command.set(self.partner_id.ids)]})
        return wizard._action_open_modal()

    def action_learning_activate(self):
        self.ensure_one()
        require_manager(self)
        self.line_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        line = self.line_id
        line.invalidate_recordset()
        if self.activated_at:
            return True  # Replays never extend access or enqueue a second message.
        now = fields.Datetime.now()
        if (
            line.state != "sale"
            or not line.learning_authorized_at
            or not line.learning_assign_until
            or now >= line.learning_assign_until
        ):
            raise ValidationError(self.env._("Commercial authorization and an open assignment period are required."))
        course = line.learning_channel_id
        course._learning_staff(manager=True)
        course.lock_for_update()
        users = self.partner_id.with_context(active_test=False).user_ids
        if (
            len(users) != 1
            or not users.active
            or users._is_public()
            or course.learning_company_id not in users.company_ids
        ):
            raise ValidationError(self.env._("Prepare the beneficiary's unique active Odoo account before activation."))
        members = self.env["slide.channel.partner"]
        member = members.with_context(active_test=False).search(
            [("channel_id", "=", course.id), ("partner_id", "=", self.partner_id.id)],
            limit=1,
        )
        if line.learning_purchase_kind == "renewal":
            if not member.learning_started_at:
                raise ValidationError(self.env._("Renewal requires an already activated membership of this edition."))
            if member.learning_state in ("suspended", "revoked"):
                raise ValidationError(self.env._("Resolve the suspended or revoked access explicitly before renewal."))
            start = max(now, member.learning_ends_at)
        else:
            if member.learning_started_at and member.learning_state in (
                "suspended",
                "revoked",
            ):
                raise ValidationError(
                    self.env._("Resolve the suspended or revoked access explicitly before adding rights.")
                )
            start = now
        end = start + relativedelta(months=line.learning_access_months)
        if not member:
            member = members.with_context({}).create({"channel_id": course.id, "partner_id": self.partner_id.id})
        self._store({"membership_id": member.id})
        union_end = max(end, member.learning_ends_at) if member.learning_started_at else end
        member.action_learning_activate(union_end, users.id, self.env._("Authorized sale seat %s", self.id))
        self._store(
            {
                "membership_id": member.id,
                "activated_at": now,
                "access_started_at": start,
                "access_ends_at": end,
            }
        )
        self._notify_activation()
        self._complete_assignment_activity()
        return True

    @api.private
    def _complete_assignment_activity(self):
        if self.assignment_activity_id:
            self.assignment_activity_id.sudo().action_feedback(
                feedback=self.env._("The learner assignment is finalized.")
            )
            self._store({"assignment_activity_id": False})

    @api.private
    def _notify_activation(self):
        try:
            with self.env.cr.savepoint():
                if not email_normalize(self.partner_id.email):
                    raise ValidationError(
                        self.env._("Check the beneficiary email before sending the access notification.")
                    )
                notice = self.env["training.elearning.reminder"]._enqueue(
                    "activation", self.membership_id, event=len(self.membership_id.learning_access_log or [])
                )
                mail_id = notice.mail_id.id if notice else False
                if not mail_id:
                    raise ValidationError(self.env._("The access notification was not queued."))
                self._store({"notification_mail_id": mail_id, "notification_state": "queued"})
        except Exception:  # A mail preparation failure must not undo the effective access start.
            self._store({"notification_state": "exception"})
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=self.env.uid,
                summary=self.env._("Check the learner access notification"),
            )

    @api.model
    def _cron_learning_notifications(self):
        # Queue status metadata only, across operating companies; no exam data.
        seats = self.sudo().search(
            [
                ("notification_state", "=", "queued"),
                ("notification_mail_id.state", "in", ["exception", "cancel"]),
            ],
            limit=100,
        )
        for seat in seats:
            seat.lock_for_update()
            seat.invalidate_recordset()
            if seat.notification_state != "queued":
                continue
            seat._store({"notification_state": "exception"})
            coordinator = seat.line_id.learning_authorized_by
            seat.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=coordinator.id if coordinator.active else self.env.ref("base.user_admin").id,
                summary=self.env._("Check the learner access notification"),
            )

    @api.ondelete(at_uninstall=False)
    def _keep_seat_history(self):
        require_manager(self)
        self.line_id.lock_for_update()
        if self.filtered("activated_at"):
            raise ValidationError(self.env._("Keep activated seat history; decide access changes explicitly."))
        self.line_id._learning_touch_allocations()


class Membership(models.Model):
    _inherit = "slide.channel.partner"

    @api.private
    def _learning_plan_source(self):
        self.ensure_one()
        pending = (
            self.env["training.elearning.sale.allocation"]
            .sudo()
            .search([("membership_id", "=", self.id), ("activated_at", "=", False)], limit=2)
        )
        if not pending:
            return super()._learning_plan_source()
        if len(pending) != 1:
            raise ValidationError(self.env._("Resolve ambiguous pending allocations before activation."))
        seat = pending.with_env(self.env)
        require_manager(seat)
        line = seat.line_id
        if (
            seat.partner_id != self.partner_id
            or line.learning_channel_id != self.channel_id
            or line.state != "sale"
            or not line.learning_authorized_at
        ):
            raise AccessError(self.env._("Use the authorized allocation of this learner and edition."))
        return line.sudo().learning_plan or super()._learning_plan_source()
