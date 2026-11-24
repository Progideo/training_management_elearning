"""The native unique channel/contact membership is the autonomous grant context."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.addons.training_catalog.models.training_deletion import require_evidence_deletion


class Membership(models.Model):
    # An administrator deletes a finished learner dossier (conservation configurée, 22 November 2026).
    _name = "slide.channel.partner"
    _inherit = ["slide.channel.partner", "training.dossier.deletion"]
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
    # Native "Course finished" karma actually credited to the learner, to withdraw it exactly
    # (lost completion, deleted dossier) even if the course setting changes afterwards.
    learning_karma_granted = fields.Integer(readonly=True, copy=False, groups="base.group_system")

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
            member._learning_completion_karma(progress["complete"])

    @api.private
    def _learning_completion_karma(self, complete):
        """Native "Course finished" karma for managed courses (gamification, 24 November 2026).

        The native completion hook is bypassed for these courses: the karma follows the
        learner's own account, is granted once per membership and withdrawn when the
        completion is lost, for instance after a motivated acquisition invalidation.
        """
        self.ensure_one()
        member = self.sudo()
        user = member.learning_user_id
        granted = member.learning_karma_granted
        karma = member.channel_id.karma_gen_channel_finish
        if complete and not granted and karma > 0 and user:
            user._add_karma(karma, member.channel_id, self.env._("Course Finished"))
            member._learning_store({"learning_karma_granted": karma})
        elif not complete and granted:
            if user:
                user._add_karma(-granted, member.channel_id, self.env._("Course Set Uncompleted"))
            member._learning_store({"learning_karma_granted": 0})

    def unlink(self):
        # A deleted learner dossier takes its course karma with it.
        for member in self.sudo().filtered(lambda m: m.learning_karma_granted and m.learning_user_id):
            user = member.learning_user_id
            # The native karma history keeps its lines (other course gains share them);
            # a compensating line removes the course points from the learner's total.
            user._add_karma(
                -member.learning_karma_granted, user, self.env._("Training points deleted with their dossier")
            )
        return super().unlink()

    def _recompute_completion(self):
        managed = self.filtered(lambda m: m.channel_id.training_course_id)
        result = super(Membership, self - managed)._recompute_completion()
        if not self.env.context.get("learning_projection_in_progress"):
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
                "member_status": self.member_status if self.learning_started_at else "joined",
            }
        )
        self._learning_sync_progress()
        from .reminder import SUPPRESS_ACTIVATION  # Local import avoids model initialization cycles.

        reminders = self.env["training.elearning.reminder"]
        if not SUPPRESS_ACTIVATION.get():
            reminders._enqueue("activation", self, event=len(log))
        for days in {
            self.channel_id.learning_company_id.learning_notice_long_days,
            self.channel_id.learning_company_id.learning_notice_short_days,
        } - {0}:
            reminders._enqueue("course_end", self, offset=days)
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

    @api.private
    def _training_unfinished(self):
        return self.filtered(lambda member: member.active and member.learning_state != "revoked")

    @api.ondelete(at_uninstall=False)
    def _learning_keep_members(self):
        members = self.filtered(lambda row: row.sudo().channel_id.training_course_id)
        require_evidence_deletion(members, self.env._("Archive access instead of deleting learner history."))


class LessonEvidence(models.Model):
    _inherit = "slide.slide.partner"
    learning_completed_at = fields.Datetime(readonly=True, copy=False)
    learning_valid_completed_at = fields.Datetime(readonly=True, copy=False)

    @api.private
    def _learning_project(self, member, slide_id, complete):
        # This flag only suppresses recursive recomputation. Public create/write
        # remain denied regardless of any context supplied by a caller.
        model = self.sudo().with_context({}, learning_projection_in_progress=True)  # pylint: disable=context-overridden
        row = model.search([("slide_id", "=", slide_id), ("partner_id", "=", member.partner_id.id)], limit=1)
        if not row:
            row = super(LessonEvidence, model).create(  # pylint: disable=super-method-mismatch
                {
                    "slide_id": slide_id,
                    "partner_id": member.partner_id.id,
                    "completed": bool(complete),
                    "learning_completed_at": fields.Datetime.now() if complete else False,
                    "learning_valid_completed_at": fields.Datetime.now() if complete else False,
                }
            )
        elif row.completed != bool(complete):
            values = {"completed": bool(complete)}
            if complete:
                values["learning_valid_completed_at"] = fields.Datetime.now()
            if complete and not row.learning_completed_at:
                values["learning_completed_at"] = fields.Datetime.now()
            super(LessonEvidence, row).write(values)  # pylint: disable=super-method-mismatch
        if complete:
            self.env["training.elearning.acquisition.invalidation"]._restore(
                member, slide_id, row.learning_valid_completed_at or row.learning_completed_at
            )
        return row

    @api.model_create_multi
    def create(self, vals_list):
        if (
            any({"learning_completed_at", "learning_valid_completed_at"} & values.keys() for values in vals_list)
            or "default_learning_completed_at" in self.env.context
            or "default_learning_valid_completed_at" in self.env.context
        ):
            raise AccessError(self.env._("Completion timestamps are recorded by the learning evidence service."))
        slides = (
            self.env["slide.slide"]
            .sudo()
            .browse([v.get("slide_id") or self.env.context.get("default_slide_id") for v in vals_list])
        )
        if slides.channel_id.filtered("training_course_id"):
            raise AccessError(self.env._("Use the controlled learning completion service."))
        return super().create(vals_list)

    def write(self, vals):
        if {"learning_completed_at", "learning_valid_completed_at"} & vals.keys():
            raise AccessError(self.env._("Keep the first server completion timestamp."))
        target = self.env["slide.slide"].sudo().browse(vals.get("slide_id"))
        if (self.sudo().channel_id | target.channel_id).filtered("training_course_id"):
            raise AccessError(self.env._("Use the controlled learning completion service."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _learning_keep_evidence(self):
        evidence = self.filtered(lambda row: row.sudo().channel_id.training_course_id)
        require_evidence_deletion(evidence, self.env._("Keep the server learning evidence."), AccessError)


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
