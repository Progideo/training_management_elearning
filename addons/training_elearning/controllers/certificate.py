"""Personal certificate consent/PDF routes and an intentionally tiny public projection."""

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, MissingError, ValidationError, LockError
from odoo.http.stream import content_disposition
from odoo.tools import format_datetime
from .portal import private
from ..models.certificate import staff


def certificate_service():
    return request.env["training.elearning.certificate.service"]


class CertificatePortal(http.Controller):
    @http.route("/my/learning-certificates", type="http", auth="user", website=True, methods=["GET"])
    def workspace(self, **kw):
        documents = certificate_service()._list()
        for document in documents:
            document["issued_at"] = format_datetime(request.env, document["issued_at"], tz=request.env.user.tz or "UTC")
        return private(
            request.render(
                "training_elearning.certificates",
                {
                    "documents": documents,
                    "consents": certificate_service()._consents(),
                    "timezone": request.env.user.tz or "UTC",
                },
            )
        )

    @http.route("/my/learning-certificates/prepare", type="http", auth="user", website=True, methods=["POST"])
    def prepare(self, **post):
        try:
            consent = certificate_service()._prepare(
                **{key: int(post.get(key) or 0) for key in ("membership_id", "registration_id", "reactivation_id")}
            )
            return private(request.redirect("/my/learning-certificates/consent/%s" % consent.id))
        except (AccessError, MissingError):
            raise request.not_found() from None
        except (ValueError, ValidationError):
            return private(
                request.make_response(
                    "La prévisualisation ne peut pas être préparée. Actualisez votre espace.", status=400
                )
            )

    @http.route(
        "/my/learning-certificates/consent/<int:consent_id>", type="http", auth="user", website=True, methods=["GET"]
    )
    def preview(self, consent_id, **kw):
        try:
            return private(
                request.render(
                    "training_elearning.certificate_consent", {"preview": certificate_service()._preview(consent_id)}
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning-certificates/consent/<int:consent_id>/decide",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
    )
    def decide(self, consent_id, **post):
        try:
            if post.get("decision") not in ("accept", "refuse"):
                raise ValidationError(request.env._("Choose an explicit decision"))
            certificate_service()._own_consent(consent_id)._decide(post["decision"] == "accept")
            return private(request.redirect("/my/learning-certificates/consent/%s" % consent_id))
        except (AccessError, MissingError):
            raise request.not_found() from None
        except (ValidationError, LockError):
            return private(
                request.make_response(
                    "Cette décision ne peut pas être enregistrée. Préparez une nouvelle prévisualisation.", status=400
                )
            )

    @http.route(
        "/my/learning-certificates/<int:document_id>/file", type="http", auth="user", website=True, methods=["GET"]
    )
    def file(self, document_id, **kw):
        try:
            document = certificate_service()._own_document(document_id)
            return private(
                request.make_response(
                    document.pdf.content,
                    headers=[
                        ("Content-Type", "application/pdf"),
                        ("Content-Disposition", content_disposition("attestation-%s.pdf" % document.reference)),
                    ],
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route("/training/learning-certificates/<int:document_id>/file", type="http", auth="user", methods=["GET"])
    def staff_file(self, document_id, **kw):
        try:
            document = request.env["training.elearning.certificate"].browse(document_id).exists()
            staff(document)
            return private(
                request.make_response(
                    document.pdf.content,
                    headers=[
                        ("Content-Type", "application/pdf"),
                        ("Content-Disposition", content_disposition("attestation-%s.pdf" % document.reference)),
                    ],
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning-certificates/<int:document_id>/disable", type="http", auth="user", website=True, methods=["POST"]
    )
    def disable(self, document_id, **post):
        try:
            certificate_service()._own_document(document_id)._disable_public(
                "Holder requested public verification deactivation", owner=True
            )
            return private(request.redirect("/my/learning-certificates"))
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/learning/certificates/<string:token>",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def public(self, token, **kw):
        response = request.render(
            "training_elearning.certificate_verification", {"verification": certificate_service()._public(token)}
        )
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return private(response)
