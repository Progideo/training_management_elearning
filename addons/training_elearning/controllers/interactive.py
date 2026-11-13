"""Owned lesson entry and saves over the single common isolated-origin player."""

import json
from uuid import uuid4
from odoo import http
from odoo.http import request
from odoo.tools import format_datetime
from odoo.exceptions import AccessError, MissingError, ValidationError, LockError
from odoo.addons.training_interactive.controllers.content import Content as CommonContent, origin
from .portal import private


class Interactive(CommonContent):
    @http.route(
        "/my/learning/<int:membership_id>/interactive/<int:slide_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def entry(self, membership_id, slide_id, **kw):
        try:
            member = request.env["training.elearning.service"]._membership(membership_id, history=True)
            item = next(
                (
                    item
                    for item in member._learning_plan()["slides"]
                    if item["id"] == slide_id and item["kind"] == "interactive"
                ),
                None,
            )
            if not item:
                raise AccessError(request.env._("This owned interactive history is unavailable."))
            available = True
            try:
                request.env["training.elearning.interactive.attempt"]._scope(membership_id, slide_id)
            except AccessError:
                available = False
            attempts = (
                request.env["training.elearning.interactive.attempt"]
                .sudo()
                .search(
                    [
                        ("membership_id", "=", membership_id),
                        ("slide_id", "=", slide_id),
                    ],
                    order="number desc",
                )
            )
            values = {
                "member_id": member.id,
                "slide_id": slide_id,
                "title": item["title"],
                "available": available,
                "request_key": str(uuid4()),
                "new_key": str(uuid4()),
                "threshold": item["threshold"] if item["rule"] == "score" else None,
                "acquired": request.env["training.elearning.service"]._item_status(member, item)["complete"],
                "timezone": request.env.user.tz or "UTC",
                "attempts": [
                    {
                        "number": attempt.number,
                        "saved_at": format_datetime(request.env, attempt.last_saved_at, tz=request.env.user.tz or "UTC")
                        if attempt.last_saved_at
                        else False,
                        "score": "%g / %g" % (attempt.score, attempt.maximum) if attempt.maximum else "Non disponible",
                    }
                    for attempt in attempts
                ],
            }
            return private(request.render("training_elearning.interactive_entry", values))
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning/<int:membership_id>/interactive/<int:slide_id>/start", type="http", auth="user", methods=["POST"]
    )
    def start(self, membership_id, slide_id, **post):
        try:
            if origin() != request.env["training.elearning.lease"]._origins()[0]:
                raise AccessError(request.env._("Launch the activity from its authorized portal origin."))
            attempt = request.env["training.elearning.interactive.attempt"]._start(
                membership_id, slide_id, post.get("request_key", ""), new=post.get("new") == "1"
            )
            return private(request.redirect("/my/learning-interactive/attempt/%s" % attempt.id, code=303))
        except (AccessError, MissingError):
            raise request.not_found() from None
        except (ValidationError, LockError):
            return private(
                request.make_response("Le lancement ne peut pas être finalisé. Actualisez cette activité.", status=409)
            )

    @http.route("/my/learning-interactive/attempt/<int:attempt_id>", type="http", auth="user", methods=["GET"])
    def attempt(self, attempt_id, **kw):
        try:
            service = request.env["training.elearning.lease"]
            portal, content = service._origins()
            if origin() != portal:
                raise AccessError(request.env._("Use the authorized portal origin."))
            attempt = request.env["training.elearning.interactive.attempt"].browse(attempt_id)
            attempt._authorize()
            lease, token = service._issue(attempt.sudo().version_id, attempt)
            return self._parent(attempt.sudo().version_id, lease, token, portal, content, attempt)
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route("/my/learning-interactive/attempt/<int:attempt_id>/save", type="http", auth="user", methods=["POST"])
    def save(self, attempt_id, **post):
        try:
            if origin() != request.env["training.elearning.lease"]._origins()[0]:
                raise AccessError(request.env._("Use the authorized portal origin."))
            raw = post.get("payload", "")
            if len(raw) > 140000:
                return private(request.make_json_response({"ok": False}, status=413))
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValidationError(request.env._("Use a valid formative report."))
            receipt = (
                request.env["training.elearning.interactive.attempt"]
                .browse(attempt_id)
                ._save(data.get("key"), data.get("revision"), data.get("data"))
            )
            return private(request.make_json_response(receipt))
        except (AccessError, MissingError):
            raise request.not_found() from None
        except (ValueError, TypeError, RecursionError, ValidationError, LockError):
            return private(
                request.make_json_response(
                    {"ok": False, "error": "La sauvegarde est refusée. Actualisez cette activité."}, status=409
                )
            )

    @http.route("/my/learning-interactive/attempt/<int:attempt_id>/renew", type="http", auth="user", methods=["POST"])
    def renew(self, attempt_id, **post):
        try:
            if origin() != request.env["training.elearning.lease"]._origins()[0]:
                raise AccessError(request.env._("Use the authorized portal origin."))
            attempt = request.env["training.elearning.interactive.attempt"].browse(attempt_id)
            attempt._authorize()
            lease = request.env["training.elearning.lease"].sudo().browse(int(post.get("lease") or 0)).exists()
            if not lease or lease.user_id != request.env.user or lease.learning_attempt_id != attempt:
                raise AccessError(request.env._("This reader authorization belongs to another context."))
            lease._renew()
            return private(request.make_json_response({"ok": True}))
        except (AccessError, MissingError, ValueError):
            raise request.not_found() from None
