"""The learner receives only their own curriculum aggregation and native course links."""

from odoo import api, fields, models
from odoo.exceptions import AccessError


class Service(models.AbstractModel):
    _name = "training.elearning.path.service"
    _description = "Private Learner Curriculum Workspace"

    @api.private
    def _registration(self, registration_id):
        registration = self.env["training.elearning.path.registration"].sudo().browse(registration_id).exists()
        user = self.env.user
        if (
            not registration
            or not user.active
            or user._is_public()
            or registration.user_id != user
            or registration.partner_id != user.partner_id
            or registration.company_id not in user.company_ids
        ):
            raise AccessError(self.env._("This personal curriculum context is unavailable."))
        return registration

    @api.private
    def _list(self):
        registrations = self.env["training.elearning.path.registration"].sudo().search([("user_id", "=", self.env.uid)])
        result = []
        for registration in registrations:
            try:
                result.append(self._view(registration.id))
            except AccessError:
                continue
        return result

    @api.private
    def _view(self, registration_id):
        registration = self._registration(registration_id)
        summary = registration._summary()
        for row in summary["rows"]:
            row["url"] = False
            if row["member"]:
                try:
                    self.env["training.elearning.service"]._membership(row["member"])
                    row["url"] = "/my/learning/%s" % row["member"]
                except AccessError:
                    row["url"] = False
        contexts = []
        now = fields.Datetime.now()
        for activation in registration.activation_ids.sorted("activated_at"):
            contexts.append(
                {
                    "start": activation.activated_at,
                    "until": activation.starts_until,
                    "paused": activation.start_paused,
                    "months": activation.access_months,
                    "courses": [
                        {
                            "title": item.course_id.name,
                            "start": item.access_started_at,
                            "end": item.access_ends_at,
                            "state": "active"
                            if item.activated_at
                            else (
                                "coordination"
                                if item.blocked_at
                                else (
                                    "expired"
                                    if now >= activation.starts_until
                                    else ("ready" if item._ready() else "waiting")
                                )
                            ),
                        }
                        for item in activation.item_ids
                    ],
                }
            )
        return {
            "id": registration.id,
            "name": registration.path_id.name,
            "introduction": registration.path_id.introduction,
            "summary": summary,
            "contexts": contexts,
        }
