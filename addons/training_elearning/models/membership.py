"""The native unique channel/contact membership is the autonomous grant context."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class Membership(models.Model):
    _inherit = "slide.channel.partner"
    learning_state = fields.Selection(
        [("pending", "Pending"), ("active", "Active"), ("suspended", "Suspended"), ("revoked", "Revoked")],
        default="pending",
        readonly=True,
        copy=False,
    )
    learning_user_id = fields.Many2one("res.users", readonly=True, ondelete="restrict", copy=False)
    learning_started_at = fields.Datetime(readonly=True, copy=False)
    learning_ends_at = fields.Datetime(readonly=True, copy=False)
    learning_access_log = fields.Json(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            course = self.env["slide.channel"].browse(
                vals.get("channel_id") or self.env.context.get("default_channel_id")
            )
            if course.sudo().training_course_id:
                course._learning_staff()
                if any(k.startswith("learning_") for k in vals) or any(
                    k.startswith("default_learning_") for k in self.env.context
                ):
                    raise AccessError(self.env._("Use controlled learner access actions."))
                vals.update(learning_state="pending", member_status="invited", completion=0, completed_slides_count=0)
        return super().create(vals_list)

    def write(self, vals):
        target = self.env["slide.channel"].sudo().browse(vals.get("channel_id"))
        if (self.sudo().channel_id | target).filtered("training_course_id") or any(
            k.startswith("learning_") for k in vals
        ):
            raise AccessError(self.env._("Use controlled learner access actions."))
        return super().write(vals)

    @api.private
    def _learning_store(self, vals):
        return super(Membership, self.sudo()).write(vals)  # pylint: disable=super-method-mismatch

    @api.private
    def _learning_freeze(self):
        pass  # Exam/content adapters capture their immutable links here.

    @api.private
    def _learning_progress(self):
        return {"required": 0, "satisfied": 0, "percentage": 0, "complete": False}

    @api.private
    def _learning_sync_progress(self):
        for member in self.filtered("learning_started_at"):
            progress = member._learning_progress()
            member._learning_store(
                {
                    "completion": progress["percentage"],
                    "completed_slides_count": progress["satisfied"],
                    "member_status": "completed"
                    if progress["complete"]
                    else ("ongoing" if progress["satisfied"] else "joined"),
                }
            )

    def _recompute_completion(self):
        managed = self.filtered(lambda m: m.channel_id.training_course_id)
        result = super(Membership, self - managed)._recompute_completion()
        managed._learning_sync_progress()
        return result

    def action_learning_access(self):
        self.ensure_one()
        self.channel_id._learning_staff(manager=True)
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.access",
            "view_mode": "form",
            "target": "new",
            "context": {"default_membership_id": self.id},
        }

    def action_learning_activate(self, ends_at, user_id=None, reason=None):
        self.ensure_one()
        self.channel_id._learning_staff(manager=True)
        self.channel_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        end = fields.Datetime.to_datetime(ends_at)
        now = fields.Datetime.now()
        if not (reason or "").strip() or not end or end <= now:
            raise ValidationError(self.env._("Provide a reason and a future access end."))
        if not self.channel_id.active or self.channel_id.learning_state != "published":
            raise ValidationError(self.env._("Publish an active course before activation."))
        user = (
            self.env["res.users"].browse(user_id)
            if user_id
            else self.partner_id.user_ids.filtered(lambda u: u.active and not u._is_public())
        )
        if (
            len(user) != 1
            or not user.active
            or user._is_public()
            or user.partner_id != self.partner_id
            or self.channel_id.learning_company_id not in user.company_ids
        ):
            raise ValidationError(self.env._("Choose the active Odoo account of this learner."))
        if self.learning_started_at:
            if user != self.learning_user_id:
                raise ValidationError(self.env._("An activated membership keeps its learner identity."))
            if self.learning_state == "active" and self.learning_ends_at > end:
                raise ValidationError(self.env._("Renewal cannot shorten active access."))
        else:
            self._learning_freeze()
        log = list(self.learning_access_log or [])
        log.append(
            {
                "actor": self.env.uid,
                "at": fields.Datetime.to_string(now),
                "state": "active",
                "reason": reason.strip(),
                "before_end": fields.Datetime.to_string(self.learning_ends_at),
                "after_end": fields.Datetime.to_string(end),
            }
        )
        self._learning_store(
            {
                "learning_state": "active",
                "learning_user_id": user.id,
                "learning_started_at": self.learning_started_at or now,
                "learning_ends_at": end,
                "learning_access_log": log,
                "active": True,
                "member_status": "joined",
            }
        )
        self._learning_sync_progress()
        return True

    @api.private
    def _learning_stop(self, state, reason):
        self.channel_id._learning_staff(manager=True)
        self.channel_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()
        if not (reason or "").strip():
            raise ValidationError(self.env._("Provide an access change reason."))
        log = list(self.learning_access_log or [])
        log.append(
            {
                "actor": self.env.uid,
                "at": fields.Datetime.to_string(fields.Datetime.now()),
                "state": state,
                "reason": reason.strip(),
            }
        )
        return self._learning_store({"learning_state": state, "learning_access_log": log})

    def action_learning_suspend(self, reason=None):
        return self._learning_stop("suspended", reason)

    def action_learning_revoke(self, reason=None):
        return self._learning_stop("revoked", reason)

    @api.ondelete(at_uninstall=False)
    def _learning_keep_members(self):
        if self.sudo().channel_id.filtered("training_course_id"):
            raise ValidationError(self.env._("Archive access instead of deleting learner history."))


class LessonEvidence(models.Model):
    _inherit = "slide.slide.partner"

    @api.model_create_multi
    def create(self, vals_list):
        slides = (
            self.env["slide.slide"]
            .sudo()
            .browse([v.get("slide_id") or self.env.context.get("default_slide_id") for v in vals_list])
        )
        if slides.channel_id.filtered("training_course_id"):
            raise AccessError(self.env._("Use the controlled learning completion service."))
        return super().create(vals_list)

    def write(self, vals):
        target = self.env["slide.slide"].sudo().browse(vals.get("slide_id"))
        if (self.sudo().channel_id | target.channel_id).filtered("training_course_id"):
            raise AccessError(self.env._("Use the controlled learning completion service."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _learning_keep_evidence(self):
        if self.sudo().channel_id.filtered("training_course_id"):
            raise AccessError(self.env._("Keep the server learning evidence."))


class LearningService(models.AbstractModel):
    _name = "training.elearning.service"
    _description = "Private Autonomous Learner Access"

    @api.private
    def _membership(self, membership_id, *, history=False, lock=False):
        member = self.env["slide.channel.partner"].sudo().browse(membership_id).exists()
        user = self.env.user
        if (
            not member
            or not member.channel_id.training_course_id
            or not user.active
            or user._is_public()
            or member.learning_user_id != user
            or member.partner_id != user.partner_id
            or member.learning_state != "active"
            or not member.active
            or not member.channel_id.active
            or member.channel_id.learning_state != "published"
            or member.channel_id.learning_company_id not in user.company_ids
            or not member.learning_started_at
            or not member.learning_ends_at
            or (not history and member.learning_ends_at <= fields.Datetime.now())
        ):
            raise AccessError(self.env._("This private course is unavailable."))
        if lock:
            member.channel_id.lock_for_update()
            member.lock_for_update()
            member.invalidate_recordset()
            return self._membership(membership_id, history=history)
        return member
