"""Native authenticated portal forms for declarations, deposits and personal rendus."""

from uuid import uuid4
from odoo import http
from odoo.exceptions import AccessError, MissingError, ValidationError, LockError
from odoo.http import request
from odoo.http.stream import content_disposition
from .portal import private
from ..models.submission_files import MIB, extensions


class PracticalPortal(http.Controller):
    @http.route(
        "/my/learning/<int:membership_id>/tasks/<int:slide_id>", type="http", auth="user", website=True, methods=["GET"]
    )
    def task(self, membership_id, slide_id, **kw):
        try:
            member, slide, task = request.env["training.elearning.practical.service"]._context(membership_id, slide_id)
            rows = (
                request.env["training.elearning.submission"]
                .sudo()
                .search(
                    [("membership_id", "=", member.id), ("slide_id", "=", slide.id)], order="received_at desc,id desc"
                )
            )
            queue = (
                request.env["training.elearning.review.queue"]
                .sudo()
                .search([("membership_id", "=", member.id), ("slide_id", "=", slide.id)], limit=1)
            )
            return private(
                request.render(
                    "training_elearning.practical_page",
                    {
                        "member": member,
                        "slide": slide,
                        "task": task,
                        "submissions": rows,
                        "queue": queue,
                        "policy": task._policy(),
                        "request_key": str(uuid4()),
                        "accept": ",".join("." + value for value in sorted(extensions(task.upload_extensions))),
                    },
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning/<int:membership_id>/tasks/<int:slide_id>/declare", type="http", auth="user", methods=["POST"]
    )
    def declare(self, membership_id, slide_id, **post):
        try:
            request.env["training.elearning.practical.service"]._declare(membership_id, slide_id)
            return private(request.redirect("/my/learning/%s" % membership_id))
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning/<int:membership_id>/tasks/<int:slide_id>/deposit",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        max_content_length=128 * MIB,
    )
    def deposit(self, membership_id, slide_id, **post):
        try:
            service = request.env["training.elearning.practical.service"]
            # Authorize before consuming file streams. Server validation still
            # rechecks and locks the grant before recording any receivable proof.
            _member, _slide, task = service._context(membership_id, slide_id, history=True)
            uploads = [file for file in request.httprequest.files.getlist("files") if file.filename]
            if not uploads or len(uploads) > task.max_files:
                raise ValidationError(service._file_error("file_count_limit", task))
            files = [(file.filename, file.stream.read(task.file_mib * MIB + 1)) for file in uploads]
            row = service._deposit(membership_id, slide_id, files, post.get("request_key"))
            return private(request.redirect("/my/learning-submissions/%s" % row.id))
        except (AccessError, MissingError):
            raise request.not_found() from None
        except (ValidationError, LockError) as error:
            return private(
                request.render(
                    "training_elearning.practical_error",
                    {"message": str(error), "back": "/my/learning/%s/tasks/%s" % (membership_id, slide_id)},
                    status=400,
                )
            )

    @http.route("/my/learning-submissions/<int:submission_id>", type="http", auth="user", website=True, methods=["GET"])
    def submission(self, submission_id, **kw):
        try:
            row = request.env["training.elearning.practical.service"]._history(submission_id)
            return private(
                request.render(
                    "training_elearning.practical_submission",
                    {
                        "submission": row,
                        "revision_open": bool(row.review_queue_id and row.review_queue_id._revision_open()),
                    },
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning-submissions/<int:submission_id>/files/<int:file_id>", type="http", auth="user", methods=["GET"]
    )
    def file(self, submission_id, file_id, **kw):
        try:
            row = request.env["training.elearning.practical.service"]._history(submission_id)
            file = row.payload_id.file_ids.filtered(lambda item: item.id == file_id)
            if (
                not file
                or file.res_model != "training.elearning.submission.payload"
                or file.res_id != row.payload_id.id
            ):
                raise request.not_found()
            return private(
                request.make_response(
                    file.raw.content,
                    headers=[
                        ("Content-Type", file.mimetype or "application/octet-stream"),
                        ("Content-Disposition", content_disposition(file.name)),
                    ],
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None
