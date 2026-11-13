"""One native named seat funds a curriculum subset; each opened course keeps its native membership."""

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .offer import require_manager, MANAGER


class Allocation(models.Model):
    _inherit = "training.elearning.sale.allocation"
    path_activation_id = fields.Many2one(
        "training.elearning.path.activation",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )

    def action_learning_activate(self):
        self.ensure_one()
        if not self.sudo().line_id.learning_path_id:
            return super().action_learning_activate()
        require_manager(self)
        self.line_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        line = self.line_id
        line.invalidate_recordset()
        if self.activated_at:
            return True
        now = fields.Datetime.now()
        if (
            line.state != "sale"
            or not line.learning_authorized_at
            or not line.learning_assign_until
            or now >= line.learning_assign_until
            or not line.learning_plan
            or line.learning_plan.get("path") != line.learning_path_id.id
        ):
            raise ValidationError(
                self.env._("Use a confirmed authorized curriculum purchase within its assignment period.")
            )
        users = self.partner_id.sudo().with_context(active_test=False).user_ids
        if len(users) != 1 or not users.active or users._is_public() or line.company_id not in users.company_ids:
            raise ValidationError(self.env._("Prepare the beneficiary unique active native Odoo account."))
        self._store({"activated_at": now, "access_started_at": now})
        self.env["training.elearning.path.activation"]._activate(
            line.learning_path_id,
            self.partner_id,
            line.sudo().learning_plan,
            line.learning_access_months,
            line.learning_path_start_months,
            self.env._("Authorized curriculum sale seat %s", self.id),
            source={"sale_allocation_id": self.id},
        )
        self._complete_assignment_activity()
        return True

    @api.private
    def _path_period_end(self):
        self.ensure_one()
        context = self.sudo().path_activation_id
        ends = context.item_ids.filtered("activated_at").mapped("access_ends_at")
        if context.item_ids.filtered(lambda item: not item.activated_at):
            ends.append(context.starts_until)
        return max(ends) if ends else context.starts_until


class Activation(models.Model):
    _inherit = "training.elearning.path.activation"
    sale_allocation_id = fields.Many2one(
        "training.elearning.sale.allocation",
        readonly=True,
        ondelete="restrict",
        copy=False,
    )
    _one_sale_seat = models.Constraint(
        "UNIQUE(sale_allocation_id)",
        "This native seat already has its curriculum activation.",
    )

    @api.private
    def _check_source(self, registration, values):
        if not values:
            return super()._check_source(registration, values)
        if set(values) != {"sale_allocation_id"}:
            raise AccessError(self.env._("Use the named authorized native sale seat."))
        seat = self.env["training.elearning.sale.allocation"].browse(values["sale_allocation_id"])
        require_manager(seat)
        line = seat.line_id
        if (
            not seat.activated_at
            or seat.partner_id != registration.partner_id
            or line.learning_path_id != registration.path_id
            or not line.learning_authorized_at
        ):
            raise AccessError(self.env._("Use the authorized curriculum context of this beneficiary and purchase."))
        return True

    @api.private
    def _bind_source(self):
        result = super()._bind_source()
        if self.sale_allocation_id:
            self.sale_allocation_id._store({"path_activation_id": self.id})
        return result

    @api.private
    def _staff(self):
        result = super()._staff()
        if self.sale_allocation_id:
            require_manager(self.sale_allocation_id)
        return result

    @api.private
    def _coordinator_group(self):
        return MANAGER if self.sale_allocation_id else super()._coordinator_group()

    @api.private
    def _authorized(self):
        if not super()._authorized():
            return False
        if not self.sale_allocation_id:
            return True
        seat = self.sudo().sale_allocation_id
        # Cancelling the accounting sale does not silently revoke already
        # authorized course starts. Coordination decides consequences explicitly.
        return bool(
            seat.path_activation_id == self
            and seat.activated_at
            and seat.line_id.learning_authorized_at
            and seat.partner_id == self.registration_id.partner_id
            and seat.line_id.learning_path_id == self.registration_id.path_id
        )


class Item(models.Model):
    _inherit = "training.elearning.path.item"

    @api.private
    def _grant_interval(self, member, now):
        if self.activation_id.sale_allocation_id.line_id.learning_purchase_kind != "renewal":
            return super()._grant_interval(member, now)
        if not member.learning_started_at:
            raise ValidationError(self.env._("A curriculum renewal requires an already activated course edition."))
        start = max(now, member.learning_ends_at)
        return start, start + relativedelta(months=self.activation_id.access_months)


class CompanyPortal(models.AbstractModel):
    _inherit = "training.elearning.company.service"

    @api.private
    def _ends_at(self, mandate):
        if not mandate.sudo().line_id.learning_path_id:
            return super()._ends_at(mandate)
        line = mandate.line_id
        ends = [seat._path_period_end() for seat in line.learning_allocation_ids if seat.path_activation_id]
        contract_end = max([line.learning_assign_until or mandate.valid_until, *ends]) + relativedelta(
            months=line.learning_report_months
        )
        return min(mandate.valid_until, contract_end)

    @api.private
    def _seat_row(self, seat, now):
        if not seat.sudo().line_id.learning_path_id:
            return super()._seat_row(seat, now)
        context = seat.path_activation_id
        if not seat.activated_at:
            state = "En attente de finalisation"
        elif not context.registration_id.user_id.active:
            state = "Indisponible"
        elif now >= seat._path_period_end():
            state = "Périodes financées terminées"
        elif context.item_ids.filtered(lambda item: not item.activated_at):
            state = "Démarrages en attente"
        else:
            state = "Cours activés"
        return {
            "beneficiary": seat.partner_id.name,
            "start": seat.access_started_at,
            "end": seat._path_period_end() if context else False,
            "state": state,
        }
