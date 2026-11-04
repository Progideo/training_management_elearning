# pylint: disable=context-overridden,super-method-mismatch  # checked snapshot factory strips caller defaults
"""Immutable native working schedules for contractual practical review deadlines."""

from datetime import UTC
from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, ValidationError

MARKERS = {"learning_review_snapshot", "learning_review_resource_id"}


def guard_children(records, values=None):
    values = values or {}
    calendars = records.sudo().calendar_id
    target = records.env["resource.calendar"].sudo().browse(values.get("calendar_id")).exists()
    if "resource_id" in records._fields and values.get("resource_id"):
        target |= records.env["resource.resource"].sudo().browse(values["resource_id"]).exists().calendar_id
    if (calendars | target).filtered("learning_review_snapshot"):
        raise ValidationError(records.env._("Keep the frozen practical correction calendar."))


class Calendar(models.Model):
    _inherit = "resource.calendar"
    learning_review_snapshot = fields.Boolean(readonly=True, copy=False)
    learning_review_resource_id = fields.Many2one("resource.resource", readonly=True, copy=False, ondelete="restrict")

    @api.model_create_multi
    def create(self, vals_list):
        if any(MARKERS & values.keys() for values in vals_list) or any(
            "default_" + name in self.env.context for name in MARKERS
        ):
            raise AccessError(self.env._("Create contract calendars through the checked practical policy."))
        return super().create(vals_list)

    def write(self, values):
        if MARKERS & values.keys():
            raise AccessError(self.env._("Keep the server contract calendar identity."))
        if self.sudo().filtered("learning_review_snapshot"):
            raise ValidationError(self.env._("Keep the frozen practical correction calendar."))
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _keep_review_calendar(self):
        if self.sudo().filtered("learning_review_snapshot"):
            raise ValidationError(self.env._("Keep the frozen practical correction calendar."))

    @api.private
    def _learning_snapshot(self, course):
        course.ensure_one()
        course._learning_staff()
        self.ensure_one()
        source = self.sudo()
        source.lock_for_update()
        source.attendance_ids.lock_for_update()
        source.global_leave_ids.lock_for_update()
        company = course.learning_company_id
        if (
            source.company_id != company
            or not source.active
            or source.calendar_type != "fixed"
            or source.hours_per_day <= 0
            or not source.attendance_ids
        ):
            raise ValidationError(self.env._("Choose an active fixed working schedule of this operating company."))
        values = source.with_context({}).copy_data(
            {
                "name": self.env._("Practical correction calendar — %s", course.name),
                "reference_calendar_id": False,
                "global_leave_ids": [Command.create(leave._copy_leave_vals()) for leave in source.global_leave_ids],
            }
        )[0]
        # No snapshot flag until native child creation and derived computations finish.
        calendar = self.sudo().with_context({}).create(values)
        calendar.flush_recordset()
        resource = (
            self.env["resource.resource"]
            .sudo()
            .with_context({})
            .create(
                {
                    "name": self.env._("Practical contract timezone — %s", course.name),
                    "resource_type": "material",
                    "company_id": company.id,
                    "calendar_id": calendar.id,
                    "tz": company.tz or "UTC",
                }
            )
        )
        super(Calendar, calendar).write(
            {
                "learning_review_snapshot": True,
                "learning_review_resource_id": resource.id,
            }
        )
        calendar._learning_deadline(fields.Datetime.now(), course.learning_review_days)
        return calendar

    @api.private
    def _learning_deadline(self, received_at, days):
        self.ensure_one()
        calendar = self.sudo()
        resource = calendar.learning_review_resource_id
        if not calendar.learning_review_snapshot or not resource or not 0 < days <= 365:
            raise ValidationError(self.env._("Check the frozen practical correction policy."))
        end = calendar.plan_hours(
            days * calendar.hours_per_day,
            received_at.replace(tzinfo=UTC),
            compute_leaves=True,
            resource=resource,
        )
        if not end:
            raise ValidationError(self.env._("The contract calendar cannot produce this correction deadline."))
        return end.astimezone(UTC).replace(tzinfo=None)


class Attendance(models.Model):
    _inherit = "resource.calendar.attendance"

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            guard_children(
                self.browse(), {"calendar_id": values.get("calendar_id", self.env.context.get("default_calendar_id"))}
            )
        return super().create(vals_list)

    def write(self, values):
        guard_children(self, values)
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _keep_review_attendances(self):
        guard_children(self)


class Leave(models.Model):
    _inherit = "resource.calendar.leaves"

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            guard_children(
                self.browse(),
                {
                    "calendar_id": values.get("calendar_id", self.env.context.get("default_calendar_id")),
                    "resource_id": values.get("resource_id", self.env.context.get("default_resource_id")),
                },
            )
        return super().create(vals_list)

    def write(self, values):
        guard_children(self, values)
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _keep_review_leaves(self):
        guard_children(self)


class Resource(models.Model):
    _inherit = "resource.resource"

    def write(self, values):
        if self.env["resource.calendar"].sudo().search_count([("learning_review_resource_id", "in", self.ids)]):
            raise ValidationError(self.env._("Keep the frozen practical calendar timezone anchor."))
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _keep_review_timezone(self):
        if self.env["resource.calendar"].sudo().search_count([("learning_review_resource_id", "in", self.ids)]):
            raise ValidationError(self.env._("Keep the frozen practical calendar timezone anchor."))
