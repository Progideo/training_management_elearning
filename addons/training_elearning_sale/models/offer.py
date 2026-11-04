"""Native product defaults become immutable commercial conditions on a sold line."""

import math
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

MANAGER = "training_elearning_sale.group_learning_sales_manager"
CONTRACT = {
    "learning_channel_id",
    "learning_access_months",
    "learning_assignment_months",
    "learning_purchase_kind",
    "learning_report_months",
}
DECISION = {
    "learning_allocation_revision",
    "learning_plan",
    "learning_confirmed_at",
    "learning_authorized_at",
    "learning_authorized_by",
    "learning_authorization_reason",
    "learning_assign_until",
}


def require_manager(records):
    if not records.env.user.active or not records.env.user.has_group(MANAGER):
        raise AccessError(records.env._("Autonomous sales coordination permission is required."))
    records.check_access("write")
    if any(record.company_id not in records.env.companies for record in records):
        raise AccessError(records.env._("Use sales in your active companies."))


class Product(models.Model):
    _inherit = "product.template"
    learning_channel_id = fields.Many2one("slide.channel", ondelete="restrict", copy=True)
    learning_access_months = fields.Integer(default=6)
    learning_assignment_months = fields.Integer(default=3)
    learning_report_months = fields.Integer(default=3)

    @api.model_create_multi
    def create(self, vals_list):
        if any(
            vals.get("learning_channel_id") or self.env.context.get("default_learning_channel_id") for vals in vals_list
        ):
            if not self.env.user.has_group(MANAGER) or not self.env.user.active:
                raise AccessError(self.env._("Autonomous sales coordination permission is required."))
        for vals in vals_list:
            course_id = vals.get("learning_channel_id") or self.env.context.get("default_learning_channel_id")
            if course_id:
                course = self.env["slide.channel"].browse(course_id)
                course._learning_staff(manager=True)
                vals.setdefault("company_id", course.learning_company_id.id)
        return super().create(vals_list)

    def write(self, vals):
        if CONTRACT & vals.keys() and (vals.get("learning_channel_id") or self.sudo().filtered("learning_channel_id")):
            if not self.env.user.has_group(MANAGER) or not self.env.user.active:
                raise AccessError(self.env._("Autonomous sales coordination permission is required."))
        if vals.get("learning_channel_id"):
            course = self.env["slide.channel"].browse(vals["learning_channel_id"])
            course._learning_staff(manager=True)
            vals = {"company_id": course.learning_company_id.id, **vals}
        return super().write(vals)

    @api.constrains(
        "learning_channel_id",
        "learning_access_months",
        "learning_assignment_months",
        "learning_report_months",
        "type",
        "company_id",
    )
    def _learning_check_product(self):
        for product in self.filtered("learning_channel_id"):
            course = product.learning_channel_id
            course._learning_staff(manager=True)
            if (
                product.type != "service"
                or product.learning_access_months <= 0
                or product.learning_assignment_months <= 0
                or product.learning_report_months <= 0
                or not course.training_course_id
                or not course.active
                or course.learning_state != "published"
                or product.company_id != course.learning_company_id
            ):
                raise ValidationError(
                    self.env._("Choose a published private course, a service and positive month durations.")
                )


class Line(models.Model):
    _inherit = "sale.order.line"
    learning_allocation_revision = fields.Integer(readonly=True, copy=False, groups=MANAGER)
    learning_plan = fields.Json(readonly=True, copy=False, groups=MANAGER)
    learning_channel_id = fields.Many2one("slide.channel", ondelete="restrict", copy=True, readonly=True)
    learning_access_months = fields.Integer(readonly=True, copy=True)
    learning_assignment_months = fields.Integer(readonly=True, copy=True)
    learning_report_months = fields.Integer(default=3, readonly=True, copy=True)
    learning_purchase_kind = fields.Selection(
        [("initial", "Initial Access"), ("renewal", "Renewal")], default="initial"
    )
    learning_authorized_at = fields.Datetime(readonly=True, copy=False, groups=MANAGER)
    learning_confirmed_at = fields.Datetime(readonly=True, copy=False)
    learning_authorized_by = fields.Many2one(
        "res.users", readonly=True, copy=False, ondelete="restrict", groups=MANAGER
    )
    learning_authorization_reason = fields.Text(readonly=True, copy=False, groups=MANAGER)
    learning_assign_until = fields.Datetime(readonly=True, copy=False, groups=MANAGER)
    learning_allocation_ids = fields.One2many(
        "training.elearning.sale.allocation", "line_id", copy=False, groups=MANAGER
    )

    @api.private
    def _learning_store(self, vals):
        return super().write(vals)  # pylint: disable=super-method-mismatch  # checked server transitions only

    @api.private
    def _learning_touch_allocations(self):
        require_manager(self)
        self.lock_for_update()
        for line in self:
            line.invalidate_recordset(["learning_allocation_revision"])
            # A technical revision, not a second seat count. Updating the locked
            # row forces stale Repeatable Read allocators to retry a fresh view.
            line._learning_store({"learning_allocation_revision": line.learning_allocation_revision + 1})

    @api.model
    def _learning_defaults(self, product_id):
        product = self.env["product.product"].browse(product_id)
        product.check_access("read")
        # Classification of product configuration only; no content or learner result is returned.
        product = product.sudo()
        return {
            "learning_channel_id": product.learning_channel_id.id,
            "learning_access_months": product.learning_access_months if product.learning_channel_id else 0,
            "learning_assignment_months": product.learning_assignment_months if product.learning_channel_id else 0,
            "learning_report_months": product.learning_report_months if product.learning_channel_id else 3,
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if DECISION & vals.keys() or any("default_" + k in self.env.context for k in DECISION):
                raise AccessError(self.env._("Use the commercial authorization action."))
            if any(
                vals.get(key) for key in CONTRACT - {"learning_purchase_kind", "learning_report_months"}
            ) and not self.env.user.has_group(MANAGER):
                raise AccessError(self.env._("Use the configured autonomous product."))
            if any("default_" + key in self.env.context for key in CONTRACT) and not self.env.user.has_group(MANAGER):
                raise AccessError(self.env._("Use the configured autonomous product."))
            product_id = vals.get("product_id") or self.env.context.get("default_product_id")
            if product_id:
                defaults = self._learning_defaults(product_id)
                if (
                    "learning_report_months" in vals
                    and not self.env.user.has_group(MANAGER)
                    and vals["learning_report_months"] != defaults["learning_report_months"]
                ):
                    raise AccessError(self.env._("Use the configured autonomous product."))
                for key, value in defaults.items():
                    vals.setdefault(key, value)
        return super().create(vals_list)

    def write(self, vals):
        managed = self.sudo().filtered("learning_channel_id")
        if vals.get("learning_channel_id") and any(line.state == "sale" or line.learning_confirmed_at for line in self):
            raise ValidationError(self.env._("Add a new sale line instead of converting an already sold line."))
        if DECISION & vals.keys():
            raise AccessError(self.env._("Use the commercial authorization action."))
        if CONTRACT & vals.keys() and not self.env.user.has_group(MANAGER):
            raise AccessError(self.env._("Use the configured autonomous product."))
        if {"product_id", "product_uom_id", "order_id", *CONTRACT} & vals.keys():
            if any(
                line.state == "sale"
                or line.learning_confirmed_at
                or line.learning_authorized_at
                or line.learning_allocation_ids
                for line in managed
            ):
                raise ValidationError(self.env._("Keep the sold course edition and commercial conditions."))
        if "product_uom_qty" in vals and managed:
            self.lock_for_update()
            if any(line.learning_authorized_at and vals["product_uom_qty"] != line.product_uom_qty for line in managed):
                raise ValidationError(
                    self.env._("Create a new sale line for changed commercially authorized quantities.")
                )
            if any(vals["product_uom_qty"] < len(line.learning_allocation_ids) for line in managed):
                raise ValidationError(self.env._("Quantity cannot be lower than the named seats."))
        if "product_id" in vals and not CONTRACT & vals.keys():
            vals = {**vals, **self._learning_defaults(vals["product_id"])}
        return super().write(vals)

    @api.constrains(
        "learning_channel_id",
        "learning_access_months",
        "learning_assignment_months",
        "learning_report_months",
        "product_uom_qty",
        "product_uom_id",
        "company_id",
        "product_id",
    )
    def _learning_check_contract(self):
        for line in self.filtered("learning_channel_id"):
            course = line.learning_channel_id.sudo()
            course.lock_for_update()
            if (
                not course.training_course_id
                or course.learning_company_id != line.company_id
                or not course.active
                or course.learning_state != "published"
                or line.product_id.type != "service"
                or line.product_uom_id != self.env.ref("uom.product_uom_unit")
                or not math.isfinite(line.product_uom_qty)
                or line.product_uom_qty < 1
                or line.product_uom_qty != int(line.product_uom_qty)
                or line.learning_access_months <= 0
                or line.learning_assignment_months <= 0
                or line.learning_report_months <= 0
            ):
                raise ValidationError(
                    self.env._("Use a published course in the sale company, whole seats and positive month durations.")
                )

    def action_learning_authorize(self, reason=None):
        require_manager(self)
        self.lock_for_update()
        self.invalidate_recordset()
        if not (reason or "").strip():
            raise ValidationError(self.env._("Provide the payment verification or commercial agreement reason."))
        for line in self:
            if not line.learning_channel_id or line.state != "sale" or not line.learning_confirmed_at:
                raise ValidationError(self.env._("Confirm this autonomous sale line before commercial authorization."))
            line._learning_check_contract()
            if not line.learning_authorized_at:
                now = fields.Datetime.now()
                line._learning_store(
                    {
                        "learning_authorized_at": now,
                        "learning_authorized_by": self.env.uid,
                        "learning_authorization_reason": reason.strip(),
                        "learning_assign_until": now + relativedelta(months=line.learning_assignment_months),
                    }
                )
        return True

    def action_learning_authorization(self):
        self.ensure_one()
        require_manager(self)
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.sale.authorization",
            "view_mode": "form",
            "target": "new",
            "context": {"default_line_id": self.id},
        }

    @api.ondelete(at_uninstall=False)
    def _learning_keep_sale_history(self):
        if any(line.learning_authorized_at or line.learning_allocation_ids for line in self.sudo()):
            raise ValidationError(self.env._("Keep commercial authorizations and named seat history."))


class Order(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        # Same locks as edition editing and activation: sold exam obligations cannot drift.
        if any(
            not line.product_id.active or not line.product_id.sale_ok
            for line in self.order_line.filtered("learning_channel_id")
        ):
            raise ValidationError(self.env._("Use an active commercial offer before confirming a new autonomous sale."))
        courses = self.sudo().order_line.learning_channel_id
        courses._learning_lock_graph()
        courses._learning_check_contents()
        self.order_line.filtered("learning_channel_id")._learning_check_contract()
        result = super().action_confirm()
        courses._learning_bind_graph()
        for line in self.order_line.filtered("learning_channel_id"):
            if not line.learning_confirmed_at:
                # Native sales may confirm a configured product. The private
                # snapshot does not grant them access to its pedagogical data.
                line.sudo()._learning_store(
                    {
                        "learning_confirmed_at": fields.Datetime.now(),
                        "learning_plan": line.learning_channel_id.sudo()._learning_plan(),
                    }
                )
        return result

    def write(self, vals):
        if {"partner_id", "company_id"} & vals.keys() and any(
            order.order_line.sudo().filtered(
                lambda line: (
                    line.learning_channel_id
                    and (line.state == "sale" or line.learning_confirmed_at or line.learning_allocation_ids)
                )
            )
            for order in self
        ):
            raise ValidationError(self.env._("Keep the customer and operating company of the sold access."))
        return super().write(vals)


class Course(models.Model):
    _inherit = "slide.channel"

    @api.private
    def _learning_before_revision(self):
        result = super()._learning_before_revision()
        # Earlier generation sold lines had no plan JSON. Capture their actual
        # references only on an explicit revision, never during module update.
        for course in self:
            lines = (
                self.env["sale.order.line"]
                .sudo()
                .search(
                    [
                        ("learning_channel_id", "=", course.id),
                        ("learning_confirmed_at", "!=", False),
                        ("learning_plan", "=", False),
                    ]
                )
            )
            if lines:
                lines.lock_for_update()
                lines._learning_store({"learning_plan": course._learning_plan()})
        return result

    @api.private
    def _learning_frozen(self):
        frozen = super()._learning_frozen()
        return frozen or bool(
            self.env["sale.order.line"]
            .sudo()
            .search_count(
                [
                    ("learning_channel_id", "in", self._learning_related_courses().ids),
                    "|",
                    ("state", "=", "sale"),
                    "|",
                    ("learning_confirmed_at", "!=", False),
                    ("learning_authorized_at", "!=", False),
                ]
            )
        )
