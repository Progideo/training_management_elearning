"""Private native lessons; all content and declarations recheck the owned grant."""

import re
from urllib.parse import urlsplit
from lxml import html
from markupsafe import Markup
from odoo import http, fields
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.http.stream import content_disposition
from odoo.tools import html_sanitize, format_datetime


def private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def article_content(slide, membership_id):
    # Use native HTML sanitation, including the stricter attribute/form policy.
    # Native attachment URLs are never passed through as bearer access links.
    root = html.fragment_fromstring(
        html_sanitize(slide.html_content or "", sanitize_attributes=True, sanitize_form=True), create_parent="div"
    )
    for node in root.xpath(".//img"):
        path = urlsplit(node.get("src", "")).path
        match = re.fullmatch(r"/web/image/(\d+)(?:-[a-fA-F0-9]+)?(?:/[^/]*)?", path)
        file = (
            request.env["ir.attachment"].sudo().browse(int(match[1])).exists()
            if match
            else request.env["ir.attachment"]
        )
        if (
            not file
            or file.res_model != "slide.slide"
            or file.res_id != slide.id
            or file.mimetype not in ("image/png", "image/jpeg", "image/gif", "image/webp")
        ):
            node.drop_tree()
        else:
            node.set("src", "/my/learning/%s/activities/%s/images/%s" % (membership_id, slide.id, file.id))
            node.attrib.pop("srcset", None)
    # A lesson may link elsewhere, but cannot embed an external form or frame.
    for node in root.xpath(".//iframe|.//form|.//object|.//embed|.//video|.//audio|.//source"):
        node.drop_tree()
    return Markup(html.tostring(root, encoding="unicode"))


class Portal(http.Controller):
    @http.route("/my/learning", type="http", auth="user", website=True, methods=["GET"])
    def workspace(self, **kw):
        candidates = (
            request.env["slide.channel.partner"]
            .sudo()
            .search(
                [("learning_user_id", "=", request.env.uid), ("learning_state", "=", "active"), ("active", "=", True)]
            )
        )
        allowed = candidates.browse()
        for member in candidates:
            try:
                request.env["training.elearning.service"]._membership(member.id, history=True)
                allowed |= member
            except AccessError:
                continue
        return private(request.render("training_elearning.workspace", {"memberships": allowed}))

    @http.route("/my/learning/<int:membership_id>", type="http", auth="user", website=True, methods=["GET"])
    def course(self, membership_id, **kw):
        try:
            service = request.env["training.elearning.service"]
            member = service._membership(membership_id, history=True)
            rows = []
            for item in member._learning_plan()["slides"]:
                available = True
                try:
                    if item["kind"] == "task":
                        request.env["training.elearning.practical.service"]._context(member.id, item["id"])
                    else:
                        service._activity(member.id, item["id"])
                except AccessError:
                    available = False
                rows.append(
                    {
                        "title": item["title"],
                        "required": item["required"],
                        "status": service._item_status(member, item),
                        "available": available,
                        "url": service._activity_url(member, item),
                    }
                )
            return private(
                request.render(
                    "training_elearning.course",
                    {
                        "member": member,
                        "rows": rows,
                        "progress": member._learning_progress(),
                        "expired": member.learning_ends_at <= fields.Datetime.now(),
                        "access_started_at": format_datetime(
                            request.env, member.learning_started_at, tz=request.env.user.tz or "UTC"
                        ),
                        "access_ends_at": format_datetime(
                            request.env, member.learning_ends_at, tz=request.env.user.tz or "UTC"
                        ),
                        "timezone": request.env.user.tz or "UTC",
                    },
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route("/my/learning/<int:membership_id>/history", type="http", auth="user", website=True, methods=["GET"])
    def history(self, membership_id, **kw):
        try:
            data = request.env["training.elearning.service"]._history(membership_id)
            tz = request.env.user.tz or "UTC"
            for row in data["rows"]:
                row["acquired_at"] = (
                    format_datetime(request.env, row["acquired_at"], tz=tz) if row["acquired_at"] else False
                )
                for entry in row["entries"]:
                    entry["date"] = format_datetime(request.env, entry["date"], tz=tz) if entry["date"] else False
            return private(request.render("training_elearning.learning_history", {"history": data, "timezone": tz}))
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning/<int:membership_id>/activities/<int:slide_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def activity(self, membership_id, slide_id, **kw):
        try:
            service = request.env["training.elearning.service"]
            member, slide, item = service._activity(membership_id, slide_id)
            if item["kind"] not in ("article", "pdf", "video"):
                raise request.not_found()
            video = False
            if item["kind"] == "video":
                if slide.video_source_type == "youtube" and re.fullmatch(r"[A-Za-z0-9_-]+", slide.youtube_id or ""):
                    video = "https://www.youtube-nocookie.com/embed/%s" % slide.youtube_id
                elif slide.video_source_type == "vimeo" and re.fullmatch(r"\d+", slide.vimeo_id or ""):
                    video = "https://player.vimeo.com/video/%s" % slide.vimeo_id
            return private(
                request.render(
                    "training_elearning.activity",
                    {
                        "member": member,
                        "slide": slide,
                        "item": item,
                        "content": article_content(slide, member.id) if item["kind"] == "article" else False,
                        "video": video,
                        "status": service._item_status(member, item),
                    },
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning/<int:membership_id>/activities/<int:slide_id>/complete",
        type="http",
        auth="user",
        methods=["POST"],
    )
    def complete(self, membership_id, slide_id, **post):
        try:
            request.env["training.elearning.service"]._declare(membership_id, slide_id)
            return private(request.redirect("/my/learning/%s" % membership_id))
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning/<int:membership_id>/activities/<int:slide_id>/pdf", type="http", auth="user", methods=["GET"]
    )
    def pdf(self, membership_id, slide_id, **kw):
        try:
            _member, slide, item = request.env["training.elearning.service"]._activity(membership_id, slide_id)
            if item["kind"] != "pdf" or not slide.binary_content:
                raise request.not_found()
            return private(
                request.make_response(
                    slide.binary_content.content,
                    headers=[
                        ("Content-Type", "application/pdf"),
                        ("Content-Disposition", content_disposition(slide.learning_filename or "%s.pdf" % slide.name)),
                    ],
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route(
        "/my/learning/<int:membership_id>/activities/<int:slide_id>/images/<int:file_id>",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def image(self, membership_id, slide_id, file_id, **kw):
        try:
            _member, slide, item = request.env["training.elearning.service"]._activity(membership_id, slide_id)
            file = request.env["ir.attachment"].sudo().browse(file_id).exists()
            reference = r"/web/image/%s(?:-[a-fA-F0-9]+)?(?:[/?\"'])" % file_id
            if (
                item["kind"] != "article"
                or not file
                or file.res_model != "slide.slide"
                or file.res_id != slide.id
                or not re.search(reference, slide.html_content or "")
                or file.mimetype not in ("image/png", "image/jpeg", "image/gif", "image/webp")
            ):
                raise request.not_found()
            return private(request.make_response(file.raw.content, headers=[("Content-Type", file.mimetype)]))
        except (AccessError, MissingError):
            raise request.not_found() from None
