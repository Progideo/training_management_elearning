"""A common-library retirement notifies only its frozen autonomous contexts."""

from odoo import api, fields, models
from .course import MANAGER


class Version(models.Model):
    _inherit = "training.elearning.version"

    @api.private
    def _withdraw_consumers(self, reason):
        result = super()._withdraw_consumers(reason)
        notices = self.env["training.elearning.reminder"]
        for version in self:
            # Exact company and frozen plan: the lesson may now point at a newer
            # version, and no later cohort or another sponsor is notified for it.
            members = (
                self.env["slide.channel.partner"]
                .sudo()
                .search(
                    [
                        ("active", "=", True),
                        ("learning_state", "=", "active"),
                        ("learning_started_at", "!=", False),
                        ("learning_ends_at", ">", fields.Datetime.now()),
                        ("channel_id.active", "=", True),
                        ("channel_id.learning_state", "=", "published"),
                        ("channel_id.learning_company_id", "=", version.company_id.id),
                    ]
                )
            )
            impacted = members.filtered(
                lambda member: any(
                    row.get("kind") == "interactive" and row.get("version") == version.id
                    for row in member._learning_plan()["slides"]
                )
            )
            for member in impacted:
                notices._enqueue("resource_withdrawal", member, event=version.id, resource_version=version)
            impacted._learning_sync_progress()
            managers = (
                self.env["res.users"]
                .sudo()
                .search([("active", "=", True), ("company_ids", "in", version.company_id.ids)])
                .filtered(lambda user: user.has_group(MANAGER))
            )
            coordinator = managers.filtered(lambda user: user.id == self.env.uid) or managers[:1]
            if coordinator:
                for course in impacted.channel_id:
                    course.sudo().activity_schedule(
                        "mail.mail_activity_data_todo",
                        user_id=coordinator.id,
                        summary=self.env._("Review affected resource, learning paths and contractual dates"),
                    )
            elif impacted:
                # The library manager can arrange coordination without receiving
                # private learner dossiers or their pedagogical results.
                version.company_id.partner_id.sudo().activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=self.env.uid,
                    summary=self.env._("Appoint learning coordination to review a withdrawn resource"),
                )
        return result
