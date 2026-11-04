# pylint: disable=context-overridden  # private delegated factories strip all portal defaults
"""Explicit purchase-scoped delegations; portal users receive scalar projections only."""

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .offer import require_manager, MANAGER

AUDIT = {"state", "granted_at", "granted_by", "revoked_at", "revoked_by"}


class Mandate(models.Model):
    _name = "training.elearning.sale.mandate"
    _description = "Explicit Enterprise Purchase Mandate"
    _rec_name = "user_id"
    line_id = fields.Many2one("sale.order.line", required=True, ondelete="restrict", index=True)
    company_id = fields.Many2one(related="line_id.company_id", store=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    valid_until = fields.Datetime(required=True)
    can_assign = fields.Boolean(default=False)
    beneficiary_ids = fields.Many2many("res.partner", string="Validated Beneficiaries")
    reason = fields.Text(required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("revoked", "Revoked")], default="draft", readonly=True, copy=False
    )
    granted_at = fields.Datetime(readonly=True, copy=False)
    granted_by = fields.Many2one("res.users", readonly=True, copy=False, ondelete="restrict")
    revocation_reason = fields.Text(copy=False)
    revoked_at = fields.Datetime(readonly=True, copy=False)
    revoked_by = fields.Many2one("res.users", readonly=True, copy=False, ondelete="restrict")
    _one_active = models.UniqueIndex(
        "(line_id, user_id) WHERE state = 'active'",
        "Revoke the existing mandate before granting another for this purchase and person.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            line = self.env["sale.order.line"].browse(vals.get("line_id") or self.env.context.get("default_line_id"))
            require_manager(line)
            if AUDIT & vals.keys() or any("default_" + key in self.env.context for key in AUDIT):
                raise AccessError(self.env._("Use the explicit mandate actions."))
        return super().create(vals_list)

    def write(self, vals):
        require_manager(self)
        self.line_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        if AUDIT & vals.keys() or (self.filtered(lambda m: m.state != "draft") and set(vals) - {"revocation_reason"}):
            raise AccessError(
                self.env._("Keep mandate history; revoke it and prepare a new mandate for changed permissions.")
            )
        return super().write(vals)

    @api.private
    def _store(self, vals):
        return super().write(vals)  # pylint: disable=super-method-mismatch  # checked server transitions

    def action_grant(self):
        self.ensure_one()
        require_manager(self)
        self.line_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        line, user = self.line_id, self.user_id
        if self.state != "draft":
            raise ValidationError(self.env._("Only a prepared mandate can be granted."))
        if (
            not line.learning_channel_id
            or not line.learning_confirmed_at
            or line.state not in ("sale", "cancel")
            or not user.active
            or user._is_public()
            or line.company_id not in user.company_ids
            or self.valid_until <= fields.Datetime.now()
            or not (self.reason or "").strip()
            or (self.can_assign and not self.beneficiary_ids)
            or any(p.company_id and p.company_id != line.company_id for p in self.beneficiary_ids)
        ):
            raise ValidationError(
                self.env._(
                    "Check the enterprise purchase, named active account, end date, reason and validated beneficiaries."
                )
            )
        return self._store({"state": "active", "granted_at": fields.Datetime.now(), "granted_by": self.env.uid})

    def action_revoke(self):
        self.ensure_one()
        require_manager(self)
        self.line_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        if self.state != "active" or not (self.revocation_reason or "").strip():
            raise ValidationError(self.env._("Provide a reason to revoke an active mandate."))
        return self._store({"state": "revoked", "revoked_at": fields.Datetime.now(), "revoked_by": self.env.uid})

    @api.ondelete(at_uninstall=False)
    def _keep_history(self):
        require_manager(self)
        self.line_id.lock_for_update()
        if self.filtered(lambda m: m.state != "draft"):
            raise ValidationError(self.env._("Keep granted and revoked mandate history."))


class CompanyPortal(models.AbstractModel):
    _name = "training.elearning.company.service"
    _description = "Private Purchase Scoped Enterprise Portal"

    @api.private
    def _ends_at(self, mandate):
        line = mandate.line_id
        if not line.learning_assign_until:
            return mandate.valid_until
        ends = line.learning_allocation_ids.filtered("activated_at").mapped("access_ends_at")
        contract_end = max([line.learning_assign_until, *ends]) + relativedelta(months=line.learning_report_months)
        return min(mandate.valid_until, contract_end)

    @api.private
    def _mandate(self, mandate_id, *, lock=False, assign=False):
        mandate = self.env["training.elearning.sale.mandate"].sudo().browse(mandate_id).exists()
        user = self.env.user
        now = fields.Datetime.now()
        if (
            not mandate
            or not user.active
            or user._is_public()
            or mandate.user_id != user
            or mandate.state != "active"
            or mandate.valid_until <= now
            or mandate.company_id not in user.company_ids
            or not mandate.granted_by.active
            or not mandate.granted_by.has_group(MANAGER)
            or mandate.company_id not in mandate.granted_by.company_ids
        ):
            raise AccessError(self.env._("This purchase mandate is unavailable."))
        line = mandate.line_id
        if now >= self._ends_at(mandate):
            raise AccessError(self.env._("This purchase mandate is unavailable."))
        if assign and (
            not mandate.can_assign
            or line.state != "sale"
            or not line.learning_authorized_at
            or not line.learning_assign_until
            or now >= line.learning_assign_until
        ):
            raise AccessError(self.env._("This purchase is unavailable for assignment."))
        if lock:
            line.lock_for_update()
            mandate.lock_for_update()
            mandate.invalidate_recordset()
            line.invalidate_recordset()
            return self._mandate(mandate_id, assign=assign)
        return mandate

    @api.private
    def _list(self):
        candidates = (
            self.env["training.elearning.sale.mandate"]
            .sudo()
            .search([("user_id", "=", self.env.uid), ("state", "=", "active")])
        )
        result = []
        for candidate in candidates:
            try:
                result.append(self._view(candidate.id))
            except AccessError:
                continue
        return result

    @api.private
    def _view(self, mandate_id):
        mandate = self._mandate(mandate_id)
        line = mandate.line_id
        seats = line.learning_allocation_ids.sorted("id")
        now = fields.Datetime.now()
        rows = []
        for seat in seats:
            if not seat.activated_at:
                state = "En attente de finalisation"
            elif now < seat.access_started_at:
                state = "Renouvellement programmé"
            elif now >= seat.access_ends_at:
                state = "Période financée terminée"
            else:
                member = seat.membership_id
                state = {"active": "Actif", "suspended": "Suspendu", "revoked": "Révoqué", "pending": "En attente"}.get(
                    member.learning_state, "À vérifier"
                )
                if (
                    not member.active
                    or not member.channel_id.active
                    or not member.learning_user_id.active
                    or member.channel_id.learning_state != "published"
                ):
                    state = "Indisponible"
            rows.append(
                {
                    "beneficiary": seat.partner_id.name,
                    "start": seat.access_started_at,
                    "end": seat.access_ends_at,
                    "state": state,
                }
            )
        assignable = bool(
            mandate.can_assign
            and line.state == "sale"
            and line.learning_authorized_at
            and line.learning_assign_until > now
        )
        allocated = {seat.partner_id.id: seat for seat in seats}
        choices = []
        if assignable:
            for partner in mandate.beneficiary_ids.sorted("id"):
                seat = allocated.get(partner.id)
                if (seat and not seat.activated_at and not seat.assigned_by) or (
                    not seat and len(seats) < line.product_uom_qty
                ):
                    choices.append({"id": partner.id, "name": partner.name})
        return {
            "id": mandate.id,
            "reference": line.order_id.name,
            "offer": line.name,
            "quantity": int(line.product_uom_qty),
            "allocated": len(seats),
            "remaining": max(0, int(line.product_uom_qty) - len(seats)),
            "valid_until": self._ends_at(mandate),
            "rows": rows,
            "assignable": assignable,
            "beneficiaries": choices,
        }

    @api.private
    def _assign(self, mandate_id, partner_id):
        mandate = self._mandate(mandate_id, lock=True, assign=True)
        if type(partner_id) is not int or partner_id not in mandate.beneficiary_ids.ids:
            raise AccessError(self.env._("This beneficiary is unavailable for this purchase."))
        partner = mandate.beneficiary_ids.filtered(lambda p: p.id == partner_id)
        if partner.company_id and partner.company_id != mandate.company_id:
            raise AccessError(self.env._("This beneficiary is unavailable for this purchase."))
        line = mandate.line_id
        # Only this already-authorized named action is delegated. No portal ACL
        # or business role is granted; the actual representative is stored below.
        issuer = mandate.granted_by
        allocations = (
            self.env["training.elearning.sale.allocation"]
            .with_user(issuer)
            .with_context(allowed_company_ids=line.company_id.ids)
        )
        existing = allocations.search([("line_id", "=", line.id), ("partner_id", "=", partner_id)], limit=1)
        if existing and (existing.activated_at or existing.assigned_by):
            return True
        seat = existing or allocations.with_context({"allowed_company_ids": line.company_id.ids}).create(
            {"line_id": line.id, "partner_id": partner_id}
        )  # pylint: disable=context-overridden  # strip all portal-supplied defaults
        seat._store({"assigned_by": self.env.uid, "assigned_mandate_id": mandate.id})
        try:
            with self.env.cr.savepoint():
                seat.action_learning_activate()
        except ValidationError:
            # Identity ambiguity, missing native account or a renewal requiring
            # coordination never discloses the learner's other relationships.
            seat.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=issuer.id,
                summary=self.env._("Finalize the mandated learner assignment"),
            )
        return True
