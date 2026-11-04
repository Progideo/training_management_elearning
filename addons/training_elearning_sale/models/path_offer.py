# pylint: disable=super-method-mismatch,context-overridden,consider-merging-classes-inherited  # curriculum contracts are kept separate from single-course contracts
"""Complete or explicitly partial curriculum offers remain native products, lines and named seats."""

import math
from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, ValidationError
from .offer import MANAGER, CONTRACT


class Product(models.Model):
    _inherit = "product.template"
    learning_path_id = fields.Many2one("training.elearning.path", ondelete="restrict", copy=True)
    learning_path_course_ids = fields.Many2many(
        "slide.channel",
        "learning_path_product_course_rel",
        "product_id",
        "course_id",
        copy=True,
    )
    learning_path_start_months = fields.Integer(default=12)

    @api.onchange("learning_path_id")
    def _onchange_learning_path(self):
        if self.learning_path_id:
            self.learning_channel_id = False
            self.learning_path_course_ids = self.learning_path_id.line_ids.course_id

    @api.onchange("learning_channel_id")
    def _onchange_learning_course(self):
        if self.learning_channel_id:
            self.learning_path_id = False
            self.learning_path_course_ids = False

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            path_id = values.get("learning_path_id") or self.env.context.get("default_learning_path_id")
            if path_id:
                if not self.env.user.active or not self.env.user.has_group(MANAGER):
                    raise AccessError(self.env._("Autonomous sales coordination permission is required."))
                path = self.env["training.elearning.path"].browse(path_id)
                path._staff(manager=True)
                values.setdefault("company_id", path.company_id.id)
                values.setdefault(
                    "learning_path_course_ids",
                    [Command.set(path.line_ids.course_id.ids)],
                )
        return super().create(vals_list)

    def write(self, values):
        managed = self.sudo().filtered(lambda product: product.learning_channel_id or product.learning_path_id)
        if CONTRACT & values.keys() and (values.get("learning_path_id") or managed.filtered("learning_path_id")):
            if not self.env.user.active or not self.env.user.has_group(MANAGER):
                raise AccessError(self.env._("Autonomous sales coordination permission is required."))
        values = dict(values)
        if values.get("learning_path_id"):
            path = self.env["training.elearning.path"].browse(values["learning_path_id"])
            path._staff(manager=True)
            values.setdefault("company_id", path.company_id.id)
            values.setdefault("learning_path_course_ids", [Command.set(path.line_ids.course_id.ids)])
        target_company = values.get("company_id")
        if values.get("learning_channel_id"):
            target_company = (
                self.env["slide.channel"].sudo().browse(values["learning_channel_id"]).learning_company_id.id
            )
        if target_company and any(product.company_id.id != target_company for product in managed):
            products = managed.product_variant_ids
            if (
                self.env["sale.order.line"]
                .sudo()
                .search_count(
                    [
                        ("product_id", "in", products.ids),
                        ("learning_confirmed_at", "!=", False),
                    ]
                )
            ):
                raise ValidationError(
                    self.env._(
                        "Create another commercial product instead of moving a sold autonomous offer to another company."
                    )
                )
        return super().write(values)

    @api.constrains(
        "learning_path_id",
        "learning_channel_id",
        "learning_path_course_ids",
        "learning_path_start_months",
        "learning_access_months",
        "learning_assignment_months",
        "learning_report_months",
        "learning_review_days",
        "learning_revision_days",
        "type",
        "company_id",
    )
    def _check_path_product(self):
        if any(not product.learning_path_id and product.learning_path_course_ids for product in self):
            raise ValidationError(self.env._("Select a curriculum for its included course selection."))
        for product in self.filtered("learning_path_id"):
            path = product.learning_path_id
            path._staff(manager=True)
            if (
                product.learning_channel_id
                or path.state != "published"
                or not path.active
                or product.company_id != path.company_id
                or product.type != "service"
                or product.learning_path_start_months <= 0
                or product.learning_access_months <= 0
                or product.learning_assignment_months <= 0
                or product.learning_report_months <= 0
                or not 0 < product.learning_review_days <= 365
                or not 0 < product.learning_revision_days <= 365
                or not product.learning_path_course_ids
                or not product.learning_path_course_ids <= path.line_ids.course_id
            ):
                raise ValidationError(
                    self.env._(
                        "Choose one published curriculum, an explicit course subset, the operating company and positive contract durations."
                    )
                )
            path._validate()


class Line(models.Model):
    _inherit = "sale.order.line"
    learning_path_id = fields.Many2one("training.elearning.path", ondelete="restrict", readonly=True, copy=True)
    learning_path_selection = fields.Json(readonly=True, copy=True)
    learning_path_course_ids = fields.Many2many(
        "slide.channel",
        compute="_compute_path_courses",
        compute_sudo=True,
    )

    @api.depends("learning_path_selection")
    def _compute_path_courses(self):
        for line in self:
            selection = line.learning_path_selection or []
            if (
                not isinstance(selection, list)
                or any(type(value) is not int or value <= 0 for value in selection)
                or len(set(selection)) != len(selection)
            ):
                raise ValidationError(self.env._("Use a list of distinct course references in the frozen selection."))
            line.learning_path_course_ids = self.env["slide.channel"].browse(selection)

    @api.model_create_multi
    def create(self, vals_list):
        if (
            any("learning_path_course_ids" in values for values in vals_list)
            or "default_learning_path_course_ids" in self.env.context
        ):
            raise AccessError(self.env._("Use the frozen configured curriculum selection."))
        return super().create(vals_list)

    def write(self, values):
        if "learning_path_course_ids" in values:
            raise AccessError(self.env._("Use the frozen configured curriculum selection."))
        return super().write(values)

    learning_path_start_months = fields.Integer(default=12, readonly=True, copy=True)

    @api.model
    def _learning_defaults(self, product_id):
        values = super()._learning_defaults(product_id)
        product = self.env["product.product"].browse(product_id)
        product.check_access("read")
        product = product.sudo()
        values.update(
            learning_path_id=product.learning_path_id.id,
            learning_path_selection=product.learning_path_course_ids.ids,
            learning_path_start_months=product.learning_path_start_months,
        )
        if product.learning_path_id:
            values.update(
                learning_access_months=product.learning_access_months,
                learning_assignment_months=product.learning_assignment_months,
                learning_report_months=product.learning_report_months,
                learning_review_days=product.learning_review_days,
                learning_revision_days=product.learning_revision_days,
            )
        return values

    @api.constrains(
        "learning_path_id",
        "learning_channel_id",
        "learning_path_selection",
        "learning_path_start_months",
        "learning_access_months",
        "learning_assignment_months",
        "learning_report_months",
        "learning_review_days",
        "learning_revision_days",
        "product_id",
        "product_uom_id",
        "product_uom_qty",
        "company_id",
    )
    def _check_path_contract(self):
        if any(not line.learning_path_id and line.learning_path_course_ids for line in self):
            raise ValidationError(self.env._("Keep the curriculum reference of its included course selection."))
        # Validate contract references under sudo without granting the native
        # salesperson any access to private course records.
        for line in self.sudo().filtered("learning_path_id"):
            path = line.sudo().learning_path_id
            if (
                line.learning_channel_id
                or not path.active
                or path.state != "published"
                or path.company_id != line.company_id
                or line.product_id.type != "service"
                or line.product_uom_id != self.env.ref("uom.product_uom_unit")
                or not math.isfinite(line.product_uom_qty)
                or line.product_uom_qty < 1
                or line.product_uom_qty != int(line.product_uom_qty)
                or line.learning_path_start_months <= 0
                or line.learning_access_months <= 0
                or line.learning_assignment_months <= 0
                or line.learning_report_months <= 0
                or not 0 < line.learning_review_days <= 365
                or not 0 < line.learning_revision_days <= 365
                or not line.learning_path_course_ids
                or not line.learning_path_course_ids <= path.line_ids.course_id
            ):
                raise ValidationError(
                    self.env._(
                        "Use a published curriculum in the sale company, an explicit subset and whole native seats."
                    )
                )
            path._validate()

    @api.private
    def _learning_check_contract(self):
        result = super()._learning_check_contract()
        self._check_path_contract()
        return result

    @api.private
    def _learning_contract_plan(self):
        self.ensure_one()
        if not self.learning_path_id:
            return super()._learning_contract_plan()
        plan = self.sudo().learning_path_id._plan(self.learning_path_course_ids.ids)
        for course_plan in plan["plans"].values():
            for item in course_plan["slides"]:
                if item.get("review_calendar"):
                    item.update(
                        review_days=self.learning_review_days,
                        revision_days=self.learning_revision_days,
                    )
        return plan

    @api.private
    def _learning_offer_terms(self):
        self.ensure_one()
        self.check_access("read")
        line = self.sudo()
        if not line._learning_managed_lines():
            return False
        included = line.learning_path_course_ids if line.learning_path_id else line.learning_channel_id
        return {
            "path": bool(line.learning_path_id),
            "courses": included.mapped("name"),
            "partial": bool(
                line.learning_path_id and set(included.ids) != set(line.learning_path_id.line_ids.course_id.ids)
            ),
            "access_months": line.learning_access_months,
            "assignment_months": line.learning_assignment_months,
            "start_months": line.learning_path_start_months if line.learning_path_id else False,
            "report_months": line.learning_report_months,
            "review_days": line.learning_review_days,
            "revision_days": line.learning_revision_days,
        }


class Order(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        lines = self.order_line.sudo().filtered("learning_path_id")
        paths = lines.learning_path_id
        paths.lock_for_update()
        for path in paths:
            path._validate()
        if any(not line.product_id.active or not line.product_id.sale_ok for line in lines):
            raise ValidationError(self.env._("Use an active commercial curriculum offer before confirming a new sale."))
        lines._check_path_contract()
        result = super().action_confirm()
        for path in paths:
            path._bind()
        for line in lines.filtered(lambda item: not item.learning_confirmed_at):
            line._learning_store(
                {
                    "learning_confirmed_at": fields.Datetime.now(),
                    "learning_plan": line._learning_contract_plan(),
                }
            )
        return result
