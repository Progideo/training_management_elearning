"""« My courses »: autonomous courses of the signed-in learner (common contribution point)."""

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.tools.misc import format_date


class TrainingMyCourses(models.AbstractModel):
    _inherit = "training.my.courses"

    @api.private
    def _learning_memberships(self, limit=50):
        user = self.env.user
        if not user.active or user._is_public():
            return self.env["slide.channel.partner"]
        candidates = (
            self.env["slide.channel.partner"]
            .sudo()
            .search(
                [("learning_user_id", "=", user.id), ("learning_state", "=", "active"), ("active", "=", True)],
                order="learning_started_at desc, id desc",
                limit=limit,
            )
        )
        allowed = candidates.browse()
        service = self.env["training.elearning.service"]
        for member in candidates:
            try:
                service._membership(member.id, history=True)
            except AccessError:
                continue
            allowed |= member
        return allowed

    @api.private
    def _has_courses(self):
        return super()._has_courses() or bool(self._learning_memberships(limit=5))

    @api.private
    def _online_rows(self):
        rows = super()._online_rows()
        now = fields.Datetime.now()
        for member in self._learning_memberships():
            completion = member.completion or 0
            if completion >= 100:
                label, button = self.env._("Completed"), self.env._("Review course")
            elif completion:
                label, button = self.env._("Ongoing"), self.env._("Continue")
            else:
                label, button = self.env._("Not started"), self.env._("Start")
            detail = []
            if member.learning_ends_at:
                local = fields.Datetime.context_timestamp(self.env.user, member.learning_ends_at)
                detail.append(self.env._("access until %(date)s", date=format_date(self.env, local.date())))
            rows.append(
                {
                    "label": label,
                    "ongoing": 0 < completion < 100,
                    "name": member.channel_id.name,
                    "detail": " · ".join(detail),
                    "progress": completion,
                    "url": "/my/learning/%s" % member.id,
                    "button": button,
                    "sort": member.learning_started_at or now,
                }
            )
        return rows

    @api.private
    def _online_url(self):
        return "/my/learning"
