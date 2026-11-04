# pylint: disable=method-required-super,super-method-mismatch,context-overridden
"""Motivated invalidation changes the native leaf; original proofs stay immutable."""

from uuid import UUID
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .human_practical import PEDAGOGY
from .certificate import source_values


def coordinator(member):
    user = member.env.user
    if not user.active or not user.has_group(PEDAGOGY):
        raise AccessError(member.env._("Pedagogical coordination permission is required."))
    member.channel_id.with_env(member.env(su=False))._learning_staff(manager=True)


class Invalidation(models.Model):
    _name = "training.elearning.acquisition.invalidation"
    _description = "Motivated Native Acquisition Invalidation"
    _rec_name = "slide_id"
    _order = "id desc"
    membership_id = fields.Many2one(
        "slide.channel.partner", required=True, readonly=True, ondelete="restrict", index=True
    )
    slide_id = fields.Many2one("slide.slide", required=True, readonly=True, ondelete="restrict")
    company_id = fields.Many2one("res.company", required=True, readonly=True, ondelete="restrict", index=True)
    reason = fields.Text(required=True, readonly=True)
    actor_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    invalidated_at = fields.Datetime(required=True, readonly=True)
    previous_valid_at = fields.Datetime(readonly=True)
    barrier = fields.Json(readonly=True, groups="base.group_system")
    restored_at = fields.Datetime(readonly=True)
    request_key = fields.Char(required=True, readonly=True)
    withdraw_certificates = fields.Boolean(readonly=True)
    certificate_ids = fields.Many2many(
        "training.elearning.certificate",
        "learning_acquisition_certificate_rel",
        "decision_id",
        "certificate_id",
        readonly=True,
    )
    needs_certificate_review = fields.Boolean(compute="_compute_certificate_review")
    _one_request = models.Constraint("UNIQUE(request_key)", "An acquisition decision request is unique.")
    _one_active = models.UniqueIndex(
        "(membership_id,slide_id) WHERE restored_at IS NULL", "This acquisition is already invalidated."
    )

    @api.depends("certificate_ids.state", "restored_at")
    def _compute_certificate_review(self):
        for event in self:
            event.needs_certificate_review = not event.restored_at and bool(
                event.certificate_ids.filtered(lambda document: document.state == "valid")
            )

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Use the motivated acquisition decision."))

    def write(self, values):
        raise AccessError(self.env._("Keep the acquisition decision history."))

    @api.ondelete(at_uninstall=False)
    def _keep_history(self):
        raise AccessError(self.env._("Keep the acquisition decision history."))

    @api.private
    def _latest(self, member, slide_id):
        return self.sudo().search([("membership_id", "=", member.id), ("slide_id", "=", slide_id)], limit=1)

    @api.private
    def _restore(self, member, slide_id, at):
        event = self._latest(member, slide_id)
        if event and not event.restored_at:
            return super(Invalidation, event).write({"restored_at": at})
        return False

    @api.private
    def _invalidate(self, member, slide_id, reason, request_key, *, withdraw_certificates=False):
        member = self.env["slide.channel.partner"].with_env(self.env(su=False)).browse(member.id).exists()
        if not member:
            raise AccessError(self.env._("This learner context is unavailable."))
        coordinator(member)
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError(self.env._("Explain the acquisition invalidation."))
        try:
            if str(UUID(request_key)) != request_key:
                raise ValueError("Invalid request")
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError(self.env._("Use a valid acquisition request.")) from error
        with self.env.cr.savepoint():
            member.channel_id.lock_for_update()
            member.lock_for_update()
            member._certificate_touch()
            item = next((item for item in member._learning_plan()["slides"] if item["id"] == slide_id), None)
            if not item:
                raise AccessError(self.env._("Choose an activity from this frozen learner context."))
            old = self.sudo().search([("request_key", "=", request_key)], limit=1)
            if old:
                if (
                    old.membership_id != member
                    or old.slide_id.id != slide_id
                    or old.reason != reason.strip()
                    or old.withdraw_certificates != withdraw_certificates
                ):
                    raise ValidationError(self.env._("This acquisition request has different contents."))
                return old
            leaf = (
                self.env["slide.slide.partner"]
                .sudo()
                .search([("slide_id", "=", slide_id), ("partner_id", "=", member.partner_id.id)], limit=1)
            )
            if not leaf.completed:
                raise ValidationError(self.env._("Only an existing acquisition can be invalidated."))
            barrier = self.env["training.elearning.service"]._acquisition_barrier(member, item)
            previous = self._latest(member, slide_id)
            if previous:
                barrier["previous_barrier"] = {
                    key: value for key, value in (previous.barrier or {}).items() if key != "previous_barrier"
                }
            event = super(Invalidation, self.sudo().with_context({})).create(
                {
                    "membership_id": member.id,
                    "slide_id": slide_id,
                    "company_id": member.channel_id.learning_company_id.id,
                    "actor_id": self.env.uid,
                    "invalidated_at": fields.Datetime.now(),
                    "reason": reason.strip(),
                    "previous_valid_at": leaf.learning_valid_completed_at or leaf.learning_completed_at,
                    "barrier": barrier,
                    "request_key": request_key,
                    "withdraw_certificates": withdraw_certificates,
                }
            )
            self.env["slide.slide.partner"]._learning_project(member, slide_id, False)
            member._learning_sync_progress()
            documents = event._affected_certificates()
            super(Invalidation, event).write({"certificate_ids": [(6, 0, documents.ids)]})
            if withdraw_certificates:
                for document in documents:
                    document.with_env(self.env(su=False))._change("withdrawn", reason.strip())
            return event

    @api.private
    def _affected_certificates(self):
        self.ensure_one()
        member = self.sudo().membership_id
        registrations = (
            self.env["training.elearning.path.registration"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("partner_id", "=", member.partner_id.id),
                    ("user_id", "=", member.learning_user_id.id),
                    ("company_id", "=", self.company_id.id),
                ]
            )
        )
        registrations = registrations.filtered(
            lambda registration: any(item["course"] == member.channel_id.id for item in registration.composition)
        )
        documents = (
            self.env["training.elearning.certificate"]
            .sudo()
            .search(
                [
                    ("state", "=", "valid"),
                    ("company_id", "=", self.company_id.id),
                    "|",
                    ("membership_id", "=", member.id),
                    ("registration_id", "in", registrations.ids),
                ]
            )
        )
        return documents.filtered(lambda document: not source_values(document)["complete"])


class LearningService(models.AbstractModel):
    _inherit = "training.elearning.service"  # pylint: disable=consider-merging-classes-inherited

    @api.private
    def _acquisition_barrier(self, member, item):
        result = {}
        if item["kind"] == "interactive":
            latest = (
                self.env["training.elearning.interactive.attempt"]
                .sudo()
                .search([("membership_id", "=", member.id), ("slide_id", "=", item["id"])], order="id desc", limit=1)
            )
            result["interactive_max_id"] = latest.id or 0
        if item["kind"] == "task":
            submissions = (
                self.env["training.elearning.submission"]
                .sudo()
                .search([("membership_id", "=", member.id), ("slide_id", "=", item["id"])])
            )
            result["submission_max_id"] = max(submissions.ids, default=0)
            reviews = self.env["training.elearning.review"].sudo().search([("submission_id", "in", submissions.ids)])
            result["human_review_max_id"] = max(reviews.ids, default=0)
        return result


class Membership(models.Model):
    # Keep the acquisition decision entry point with its authorization policy.
    _inherit = "slide.channel.partner"  # pylint: disable=consider-merging-classes-inherited

    def action_learning_invalidate_acquisition(self):
        self.ensure_one()
        coordinator(self)
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.acquisition.invalidate",
            "view_mode": "form",
            "target": "new",
            "context": {"default_membership_id": self.id},
        }
