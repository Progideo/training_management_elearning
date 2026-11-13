"""No public URL, invitation token, package execution or remote URL fetch."""
from odoo import http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request
from odoo.http.stream import content_disposition
from odoo.addons.training_elearning.controllers.portal import private


class Resources(http.Controller):
    @http.route("/my/learning/<int:membership_id>/activities/<int:slide_id>/resources/<int:resource_id>",
                type="http", auth="user", website=True, methods=["GET"])
    def resource(self, membership_id, slide_id, resource_id, **kw):
        try:
            resource, snapshot = request.env["training.elearning.resource.service"]._context(
                membership_id, slide_id, resource_id)
            if snapshot["type"] == "url":
                # A normal external navigation, never server-side retrieval/embedding.
                return private(request.redirect(snapshot["link"], code=303, local=False))
            return private(request.make_response(resource.with_context(bin_size=False).data.content, headers=[
                ("Content-Type", snapshot["mimetype"]),
                ("Content-Disposition", content_disposition(snapshot["filename"])),
                ("Content-Security-Policy", "sandbox; default-src 'none'"),
            ]))
        except (AccessError, MissingError, ValidationError):
            raise request.not_found() from None
