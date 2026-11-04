"""The targeted revision exception never becomes a general expired-course grant."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from .human_practical import REVIEWER, valid_reviewer


class Payload(models.Model):
    _inherit = "training.elearning.submission.payload"

    @api.private
    def _extra_reader(self):
        user = self.env.user
        return bool(
            user.active
            and user.has_group(REVIEWER)
            and self
            and all(
                row.sudo().submission_id.review_queue_id.reviewer_id == user
                and valid_reviewer(user, row.sudo().company_id, row.sudo().submission_id.membership_id.learning_user_id)
                for row in self
            )
        )

    @api.private
    def _file_read_domain(self):
        domain = super()._file_read_domain()
        user = self.env.user
        if user.active and user.has_group(REVIEWER):
            domain |= (
                Domain("submission_id.review_queue_id.reviewer_id", "=", user.id)
                & Domain("submission_id.membership_id.learning_user_id", "!=", user.id)
                & Domain("company_id", "in", (self.env.companies & user.company_ids).ids)
            )
        return domain


class PracticalService(models.AbstractModel):
    _inherit = "training.elearning.practical.service"

    @api.private
    def _context(self, membership_id, slide_id, *, history=False, lock=False):
        if history:
            return super()._context(membership_id, slide_id, history=True, lock=lock)
        # Ownership, suspension and company checks remain authoritative even
        # for a targeted exception. No generic course or lesson route uses it.
        member, slide, task = super()._context(membership_id, slide_id, history=True, lock=lock)
        queue = (
            self.env["training.elearning.review.queue"]
            .sudo()
            .search(
                [
                    ("membership_id", "=", member.id),
                    ("slide_id", "=", slide.id),
                ],
                limit=1,
            )
        )
        if member.learning_ends_at <= fields.Datetime.now():
            if task.criterion != "human" or not queue or not queue._revision_open() or not slide._learning_available():
                raise AccessError(self.env._("This targeted practical revision is unavailable."))
        else:
            self.env["training.elearning.service"]._activity(membership_id, slide_id)
        if task.criterion == "human":
            if queue:
                if not valid_reviewer(
                    queue.reviewer_id, member.channel_id.learning_company_id, member.learning_user_id
                ):
                    raise AccessError(self.env._("The pedagogical coordinator must reassign an active reviewer."))
            else:
                try:
                    slide._learning_check_reviewer(member.learning_user_id)
                except ValidationError as error:
                    raise AccessError(self.env._("This practical awaits an authorized reviewer.")) from error
        return member, slide, task

    @api.private
    def _after_deposit(self, submission, task):
        if task.criterion != "human":
            return super()._after_deposit(submission, task)
        member = submission.membership_id
        item = next(item for item in member._learning_plan()["slides"] if item["id"] == submission.slide_id.id)
        self.env["training.elearning.review.queue"]._accept(submission, item)
        return False


class Service(models.AbstractModel):
    _inherit = "training.elearning.service"

    @api.private
    def _item_status(self, member, item):
        status = super()._item_status(member, item)
        if item.get("kind") == "task" and not status["complete"]:
            queue = (
                self.env["training.elearning.review.queue"]
                .sudo()
                .search(
                    [
                        ("membership_id", "=", member.id),
                        ("slide_id", "=", item["id"]),
                    ],
                    limit=1,
                )
            )
            if queue:
                status["state"] = queue.state
                status["waiting_correction"] = queue.state == "pending"
                status["revision_requested"] = queue.state in ("revision", "delivery")
        return status
