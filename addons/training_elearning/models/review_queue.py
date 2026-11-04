# pylint: disable=super-method-mismatch,context-overridden,method-required-super
"""One pending practical candidate, immutable human judgements and a stable first receipt."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from .human_practical import PEDAGOGY, REVIEWER, valid_reviewer


class Queue(models.Model):
    _name = "training.elearning.review.queue"
    _description = "Practical Human Review Queue"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "practical_id"
    membership_id = fields.Many2one("slide.channel.partner", required=True, readonly=True, ondelete="restrict")
    slide_id = fields.Many2one("slide.slide", required=True, readonly=True, ondelete="restrict")
    practical_id = fields.Many2one("training.elearning.practical", required=True, readonly=True, ondelete="restrict")
    company_id = fields.Many2one(related="membership_id.channel_id.learning_company_id")
    learner_name = fields.Char(related="membership_id.partner_id.name")
    reviewer_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    submission_id = fields.Many2one("training.elearning.submission", required=True, readonly=True, ondelete="restrict")
    first_received_at = fields.Datetime(required=True, readonly=True)
    due_at = fields.Datetime(required=True, readonly=True)
    state = fields.Selection(
        [
            ("pending", "Pending Review"),
            ("revision", "Revision Requested"),
            ("delivery", "Feedback Delivery Pending"),
            ("validated", "Validated"),
            ("closed", "Closed Without Validation"),
        ],
        readonly=True,
        default="pending",
    )
    review_id = fields.Many2one("training.elearning.review", readonly=True, ondelete="restrict")
    revision_until = fields.Datetime(readonly=True)
    late_submission_used = fields.Boolean(readonly=True)
    assignment_log = fields.Json(readonly=True)
    _one_queue = models.Constraint(
        "UNIQUE(membership_id, slide_id)", "This practical context already has a review queue."
    )

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Practical queues are created by receivable learner submissions."))

    def write(self, values):
        raise AccessError(self.env._("Use the checked practical review and reassignment actions."))

    @api.ondelete(at_uninstall=False)
    def _keep_queue(self):
        raise AccessError(self.env._("Keep practical review history."))

    @api.private
    def _store(self, values):
        return super(Queue, self.sudo()).write(values)

    @api.private
    def _lock(self):
        self.ensure_one()
        self.sudo().membership_id.channel_id.lock_for_update()
        self.sudo().membership_id.lock_for_update()
        self.lock_for_update()
        self.invalidate_recordset()

    @api.private
    def _authorize(self, *, review=False):
        self.ensure_one()
        self.check_access("read")
        user, queue = self.env.user, self.sudo()
        if (
            not user.active
            or queue.company_id not in user.company_ids
            or queue.company_id not in self.env.companies
            or not (user.has_group(PEDAGOGY) or (user.has_group(REVIEWER) and queue.reviewer_id == user))
        ):
            raise AccessError(self.env._("This private review assignment is unavailable."))
        if review and not (
            queue.reviewer_id == user and valid_reviewer(user, queue.company_id, queue.membership_id.learning_user_id)
        ):
            raise AccessError(self.env._("Only the current authorized reviewer can publish this judgement."))

    @api.private
    def _accept(self, submission, item):
        member, slide, task = submission.membership_id, submission.slide_id, submission.practical_id
        if self.env.user != member.learning_user_id or task.criterion != "human":
            raise AccessError(self.env._("Use the human practical context of this learner."))
        self.env["training.elearning.service"]._membership(member.id, history=True, lock=True)
        queue = self.sudo().search([("membership_id", "=", member.id), ("slide_id", "=", slide.id)], limit=1)
        late = submission.received_at >= member.learning_ends_at
        if queue:
            queue._lock()
            if late and not queue._revision_open():
                raise AccessError(self.env._("This targeted revision window is unavailable."))
            reviewer = queue.reviewer_id
            if not valid_reviewer(reviewer, member.channel_id.learning_company_id, member.learning_user_id):
                raise ValidationError(self.env._("The pedagogical coordinator must reassign an active reviewer."))
        else:
            if late:
                raise AccessError(self.env._("A first practical deposit requires active course access."))
            reviewer = slide._learning_check_reviewer(member.learning_user_id)
        pending = bool(queue and queue.state == "pending")
        # Preserve the feedback that originated this revision cycle, including
        # replacement candidates. It cannot be reconstructed from the mutable
        # queue once another purchase funds later practical work.
        submission._store(
            {
                "revision_parent_id": (queue.submission_id.revision_parent_id.id if pending else queue.review_id.id)
                if queue
                else False
            }
        )
        calendar = self.env["resource.calendar"].sudo().browse(item.get("review_calendar")).exists()
        if not calendar or calendar.company_id != member.channel_id.learning_company_id:
            raise ValidationError(self.env._("Check the frozen practical contract calendar."))
        values = {
            "submission_id": submission.id,
            "state": "pending",
            "review_id": False,
            "revision_until": False,
            "late_submission_used": late,
        }
        if not pending:
            values.update(
                first_received_at=submission.received_at,
                due_at=calendar._learning_deadline(submission.received_at, item.get("review_days", 5)),
            )
        if queue:
            queue._store(values)
        else:
            values.update(membership_id=member.id, slide_id=slide.id, practical_id=task.id, reviewer_id=reviewer.id)
            queue = super(Queue, self.sudo().with_context({})).create(values)
        submission._store({"review_queue_id": queue.id})
        self.env["training.elearning.review.notice"]._assignment(queue)
        self.env["training.elearning.reminder"]._schedule_queue(queue)
        return queue

    def action_prepare_review(self):
        self._authorize(review=True)
        self._lock()
        if self.state != "pending":
            raise ValidationError(self.env._("Open the current pending practical candidate."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.review.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_queue_id": self.id},
        }

    def action_prepare_reassignment(self):
        self._authorize()
        if not self.env.user.has_group(PEDAGOGY):
            raise AccessError(self.env._("Only pedagogical coordination reassigns a reviewer."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "training.elearning.review.reassign",
            "view_mode": "form",
            "target": "new",
            "context": {"default_queue_id": self.id},
        }

    @api.private
    def _reassign(self, reviewer, reason):
        self._authorize()
        if not self.env.user.has_group(PEDAGOGY):
            raise AccessError(self.env._("Only pedagogical coordination reassigns a reviewer."))
        self._lock()
        queue = self.sudo()
        if not (reason or "").strip() or not valid_reviewer(
            reviewer, queue.company_id, queue.membership_id.learning_user_id
        ):
            raise ValidationError(self.env._("Choose an active authorized reviewer and explain the reassignment."))
        if reviewer == queue.reviewer_id:
            return True
        log = list(queue.assignment_log or [])
        log.append(
            {
                "at": fields.Datetime.to_string(fields.Datetime.now()),
                "actor": self.env.uid,
                "before": queue.reviewer_id.id,
                "after": reviewer.id,
                "reason": reason.strip(),
            }
        )
        queue._store({"reviewer_id": reviewer.id, "assignment_log": log})
        if queue.state == "pending":
            self.env["training.elearning.review.notice"]._assignment(queue)
        return True

    @api.private
    def _publish(self, submission_id, outcome, results, feedback):
        self._authorize(review=True)
        self._lock()
        queue = self.sudo()
        old = self.env["training.elearning.review"].sudo().search([("submission_id", "=", submission_id)], limit=1)
        if old and old.queue_id == queue:
            return old
        if queue.state != "pending" or queue.submission_id.id != submission_id:
            raise ValidationError(self.env._("A newer submission replaced this candidate; reopen the current review."))
        if outcome not in ("validated", "revision") or not (feedback or "").strip() or not isinstance(results, dict):
            raise ValidationError(self.env._("Provide the rubric judgement and individual feedback."))
        rubric = queue.practical_id.rubric_ids
        if set(results) != {str(line.id) for line in rubric} or any(
            type(value) is not bool for value in results.values()
        ):
            raise ValidationError(self.env._("Assess each criterion of the applicable rubric exactly once."))
        if outcome == "validated" and any(line.required and not results[str(line.id)] for line in rubric):
            raise ValidationError(self.env._("Satisfy every required rubric criterion before validation."))
        member = queue.membership_id
        late_used = queue.late_submission_used and fields.Datetime.now() >= member.learning_ends_at
        values = {
            "queue_id": queue.id,
            "submission_id": submission_id,
            "reviewer_id": self.env.uid,
            "outcome": outcome,
            "feedback": feedback.strip(),
            "published_at": fields.Datetime.now(),
            "rubric_results": [
                {
                    "id": line.id,
                    "criterion": line.description,
                    "required": line.required,
                    "satisfied": results[str(line.id)],
                }
                for line in rubric
            ],
            "revision_eligible": outcome == "revision" and not late_used,
        }
        review = self.env["training.elearning.review"]._publish_record(values)
        queue._store(
            {
                "review_id": review.id,
                "state": "validated" if outcome == "validated" else ("delivery" if late_used else "revision"),
                "revision_until": False,
            }
        )
        queue.submission_id._store({"review_id": review.id})
        if outcome == "validated":
            self.env["slide.slide.partner"]._learning_project(member, queue.slide_id.id, True)
            member._learning_sync_progress()
        self.env["training.elearning.review.notice"]._feedback(review)
        return review

    @api.private
    def _revision_open(self):
        self.ensure_one()
        queue = self.sudo()
        if queue.state != "revision" or not queue.review_id or queue.late_submission_used:
            return False
        queue.review_id._sync_delivery()
        return bool(
            queue.review_id.delivery_notice_id.state == "sent"
            and not queue.review_id.delivery_notice_id.failed
            and queue.revision_until
            and fields.Datetime.now() < queue.revision_until
        )

    @api.model
    def _cron_review_closure(self):
        queues = self.sudo().search([("state", "in", ("revision", "delivery"))], limit=100)
        for queue in queues:
            queue._lock()
            queue.review_id._sync_delivery()
            notice = queue.review_id.delivery_notice_id
            if notice.state != "sent" or notice.failed:
                continue
            if queue.state == "delivery" or (queue.revision_until and fields.Datetime.now() >= queue.revision_until):
                queue._store({"state": "closed"})


class Review(models.Model):
    _name = "training.elearning.review"
    _description = "Published Private Practical Judgement"
    _rec_name = "published_at"
    queue_id = fields.Many2one("training.elearning.review.queue", required=True, readonly=True, ondelete="restrict")
    company_id = fields.Many2one(related="queue_id.company_id")
    submission_id = fields.Many2one("training.elearning.submission", required=True, readonly=True, ondelete="restrict")
    reviewer_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    published_at = fields.Datetime(required=True, readonly=True)
    outcome = fields.Selection(
        [("validated", "Validated"), ("revision", "Revision Requested")], required=True, readonly=True
    )
    feedback = fields.Text(required=True, readonly=True)
    rubric_results = fields.Json(required=True, readonly=True)
    rubric_summary = fields.Text(compute="_compute_rubric_summary")
    revision_eligible = fields.Boolean(readonly=True)
    delivery_notice_id = fields.Many2one("training.elearning.review.notice", readonly=True, ondelete="restrict")
    _one_judgement = models.Constraint(
        "UNIQUE(submission_id)", "This practical submission already has its published judgement."
    )

    @api.depends("rubric_results")
    def _compute_rubric_summary(self):
        for review in self:
            review.rubric_summary = "\n".join(
                "%s — %s" % (row["criterion"], self.env._("Satisfied") if row["satisfied"] else self.env._("To Revise"))
                for row in (review.rubric_results or [])
            )

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(self.env._("Publish a judgement through the assigned practical review."))

    def write(self, values):
        raise AccessError(self.env._("Keep published human judgements immutable."))

    @api.ondelete(at_uninstall=False)
    def _keep_review(self):
        raise AccessError(self.env._("Keep published human judgements."))

    @api.private
    def _publish_record(self, values):
        return super(Review, self.sudo().with_context({})).create(values)

    @api.private
    def _store_notice(self, notice):
        return super(Review, self.sudo()).write({"delivery_notice_id": notice.id})

    @api.private
    def _sync_delivery(self):
        self.sudo().delivery_notice_id._sync()


class Submission(models.Model):
    _inherit = "training.elearning.submission"
    learner_name = fields.Char(related="membership_id.partner_id.name")
    review_queue_id = fields.Many2one("training.elearning.review.queue", readonly=True, ondelete="restrict")
    review_id = fields.Many2one("training.elearning.review", readonly=True, ondelete="restrict")
    revision_parent_id = fields.Many2one("training.elearning.review", readonly=True, ondelete="restrict")
