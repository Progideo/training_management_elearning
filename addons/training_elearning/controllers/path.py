"""Native authenticated curriculum pages with no independent content grant."""

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, MissingError
from odoo.tools import format_datetime
from .portal import private


class PathPortal(http.Controller):
    @http.route("/my/learning-paths", type="http", auth="user", website=True, methods=["GET"])
    def paths(self, **kw):
        return private(
            request.render(
                "training_elearning.path_workspace",
                {"paths": request.env["training.elearning.path.service"]._list()},
            )
        )

    @http.route(
        "/my/learning-paths/<int:registration_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def path(self, registration_id, **kw):
        try:
            data = request.env["training.elearning.path.service"]._view(registration_id)
            tz = request.env.user.tz or "UTC"

            def display(value):
                return format_datetime(request.env, value, tz=tz) if value else ""

            data["timezone"] = tz
            data["summary"]["completed_at"] = display(data["summary"]["completed_at"])
            for context in data["contexts"]:
                context["start"], context["until"] = (
                    display(context["start"]),
                    display(context["until"]),
                )
                for course in context["courses"]:
                    course["start"], course["end"] = (
                        display(course["start"]),
                        display(course["end"]),
                    )
            return private(request.render("training_elearning.path_page", {"path": data}))
        except (AccessError, MissingError):
            raise request.not_found() from None
