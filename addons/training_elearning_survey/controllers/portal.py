"""Native authentication, CSRF, Survey widgets and the shared strict server clock."""

import json
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.tools.mimetypes import guess_mimetype
from werkzeug.exceptions import BadRequest


def private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


class Portal(http.Controller):
    @http.route(
        "/my/learning/<int:membership_id>/exams/<int:slide_id>",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
    )
    def exam(self, membership_id, slide_id, **kw):
        try:
            member, _slide, _item = request.env["training.elearning.service"]._activity(membership_id, slide_id)
            service = request.env["training.elearning.exam.service"]
            row = service._requirement(member, slide_id)
            if request.httprequest.method == "POST":
                attempt = service._start(member.id, slide_id)
                return request.redirect("/my/learning-exams/%s" % attempt.id)
            attempts = (
                request.env["survey.user_input"]
                .sudo()
                .search(
                    [("learning_membership_id", "=", member.id), ("survey_id", "=", row.exam_id.id)], order="id desc"
                )
            )
            return private(
                request.render(
                    "training_elearning_survey.exam_start", {"member": member, "row": row, "attempts": attempts}
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None
        except ValidationError as error:
            return private(request.make_response(str(error), status=400))

    @http.route("/my/learning-exams/<int:attempt_id>", type="http", auth="user", website=True, methods=["GET"])
    def attempt(self, attempt_id, **kw):
        try:
            service = request.env["training.elearning.exam.service"]
            answer = service._attempt(attempt_id)
            if answer.learning_interrupted_at:
                return private(request.render("training_elearning_survey.interrupted", {"attempt": answer}))
            return private(
                request.render(
                    "training_mock_exam.exam_attempt",
                    {
                        "answer": answer,
                        "survey": answer.survey_id,
                        "question": False,
                        "page": False,
                        "survey_data": False,
                        "scoring_display_correction": False,
                        "survey_form_readonly": False,
                        "use_half_col_lg": "",
                        "letters": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                        "useKeySelection": False,
                        "is_post_submit_question": False,
                        "server_time": fields.Datetime.now(),
                        "result": service._result(answer) if answer.state == "done" else False,
                        "can_retake": answer.survey_id.active,
                        "back": "/my/learning/%s/exams/%s"
                        % (answer.learning_membership_id.id, answer.learning_slide_id.id),
                        "save_url": "/my/learning-exams/%s/save" % answer.id,
                        "image_url": lambda question, choice: (
                            "/my/learning-exams/%s/image/%s/%s" % (answer.id, question, choice)
                        ),
                    },
                )
            )
        except (AccessError, MissingError):
            raise request.not_found() from None

    @http.route("/my/learning-exams/<int:attempt_id>/save", type="http", auth="user", methods=["POST"])
    def save(self, attempt_id, **post):
        try:
            service = request.env["training.elearning.exam.service"]
            kind = post.get("kind", "save")
            if kind == "submit":
                data = service._submit(attempt_id)
            elif kind == "status":
                answer = service._attempt(attempt_id, mutate=True)
                data = {
                    "done": answer.state == "done",
                    "remaining": max(0, int((answer.deadline - fields.Datetime.now()).total_seconds())),
                }
            elif kind == "save":
                choices = json.loads(post.get("choices", "[]"))
                if not isinstance(choices, list) or any(type(c) is not int for c in choices):
                    raise BadRequest()
                data = service._save(attempt_id, int(post["question"]), choices, post.get("marked") == "1")
            else:
                raise BadRequest()
            return private(request.make_json_response(data))
        except (AccessError, MissingError):
            raise request.not_found() from None
        except (ValueError, KeyError, ValidationError):
            raise BadRequest() from None

    @http.route(
        "/my/learning-exams/<int:attempt_id>/image/<int:question_id>/<int:choice_id>",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def image(self, attempt_id, question_id, choice_id, **kw):
        try:
            answer = request.env["training.elearning.exam.service"]._attempt(attempt_id)
            question = answer.predefined_question_ids.filtered(lambda q: q.id == question_id)
            choice = question.suggested_answer_ids.filtered(lambda c: c.id == choice_id)
            if not choice or not choice.value_image:
                raise request.not_found()
            content = choice.value_image.content
            return private(
                request.make_response(content, headers=[("Content-Type", guess_mimetype(content, default="image/png"))])
            )
        except (AccessError, MissingError):
            raise request.not_found() from None
