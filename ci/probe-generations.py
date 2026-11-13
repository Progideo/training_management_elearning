# ruff: noqa: F821  # Odoo shell supplies env
"""Real older-generation records: exact old columns/bytes, then explicit revision."""

import io
import hashlib
import json
from odoo import Command
from odoo.tests import new_test_user
from odoo.tools import BinaryBytes
from odoo.tools.pdf import PdfFileWriter

assert env.cr.dbname == "tm_suite_test"
key = "autonomous.generation.upgrade"
params = env["ir.config_parameter"]
saved = params.get_str(key)
if not saved:
    assert "learning_bound_at" not in env["slide.channel"]._fields
    assert "learning_plan" not in env["sale.order.line"]._fields
    manager = new_test_user(
        env, login="fictional_generation_sales", groups="training_elearning_sale.group_learning_sales_manager"
    )
    author = new_test_user(
        env, login="fictional_generation_author", groups="training_elearning_survey.group_learning_exam_reader"
    )
    learner = new_test_user(env, login="fictional_generation_learner", groups="base.group_portal")
    later = new_test_user(env, login="fictional_generation_later_learner", groups="base.group_portal")
    catalog = env["training.course"].create({"name": "Fictional prior generation catalogue"})
    exam = (
        env["survey.survey"]
        .with_user(author)
        .create(
            {
                "title": "Fictional retained generation version",
                "training_course_id": catalog.id,
                "time_limit": 30,
                "scoring_success_min": 75,
            }
        )
    )
    question = (
        env["survey.question"]
        .with_user(author)
        .create(
            {
                "survey_id": exam.id,
                "title": "Fictional retained question",
                "question_type": "simple_choice",
                "answer_score": 2,
                "suggested_answer_ids": [
                    Command.create({"value": "Expected", "is_correct": True}),
                    Command.create({"value": "Other"}),
                ],
            }
        )
    )
    exam.action_mock_publish()
    course = (
        env["slide.channel"]
        .with_user(author)
        .create({"name": "Fictional previous generation edition", "training_course_id": catalog.id})
    )
    article = (
        env["slide.slide"]
        .with_user(author)
        .create(
            {
                "channel_id": course.id,
                "name": "Fictional retained article",
                "slide_category": "article",
                "html_content": "<p>PRIVATE PREVIOUS GENERATION ARTICLE</p>",
                "is_published": True,
            }
        )
    )
    slide = (
        env["slide.slide"]
        .with_user(author)
        .create(
            {"channel_id": course.id, "survey_id": exam.id, "is_published": True, "learning_exam_obligation": "pass"}
        )
    )
    pdf_data = io.BytesIO()
    writer = PdfFileWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(pdf_data)
    env["slide.slide"].with_user(author).create(
        {
            "channel_id": course.id,
            "name": "Fictional retained private PDF",
            "slide_category": "document",
            "source_type": "local_file",
            "binary_content": BinaryBytes(pdf_data.getvalue()),
            "learning_optional": True,
            "is_published": True,
        }
    )
    course.action_learning_publish()
    product = (
        env["product.product"]
        .with_user(manager)
        .create({"name": "Fictional previous generation product", "type": "service", "learning_channel_id": course.id})
    )
    buyer = env["res.partner"].create({"name": "Fictional prior generation buyer"})
    order = (
        env["sale.order"]
        .with_user(manager)
        .create(
            {"partner_id": buyer.id, "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 2})]}
        )
    )
    order.action_confirm()
    line = order.order_line
    line.action_learning_authorize("Fictional prior generation commercial agreement")
    seat_model = env["training.elearning.sale.allocation"].with_user(manager)
    seat = seat_model.create({"line_id": line.id, "partner_id": learner.partner_id.id})
    seat.action_learning_activate()
    pending = seat_model.create({"line_id": line.id, "partner_id": later.partner_id.id})
    member = seat.membership_id
    env["training.elearning.service"].with_user(learner)._declare(member.id, article.id)
    service = env["training.elearning.exam.service"].with_user(learner)
    attempt = service._start(member.id, slide.id)
    service._save(attempt.id, question.id, question.suggested_answer_ids.filtered("is_correct").ids, False)
    assert member.completion == 50 and attempt.state == "in_progress"
    params.set_str(
        key,
        json.dumps(
            {
                "author": author.id,
                "manager": manager.id,
                "learner": learner.id,
                "later": later.id,
                "line": line.id,
                "slide": slide.id,
                "member": member.id,
                "pending": pending.id,
                "attempt": attempt.id,
            }
        ),
    )


def snapshot():
    env.flush_all()
    result = {}
    for table in (
        "slide_channel",
        "slide_slide",
        "slide_channel_partner",
        "slide_slide_partner",
        "survey_survey",
        "survey_user_input",
        "survey_user_input_line",
        "training_elearning_exam_requirement",
        "sale_order_line",
        "training_elearning_sale_allocation",
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id")
        result[table] = [row[0] for row in env.cr.fetchall()]
    files = env["ir.attachment"].search([("res_model", "in", ["slide.slide", "slide.channel"])])
    result["file_bytes"] = {str(file.id): hashlib.sha256(file.raw.content).hexdigest() for file in files}
    return result


if not saved:
    params.set_str(key + ".snapshot", json.dumps(snapshot(), sort_keys=True, default=str))
    env.cr.commit()
    print("PREVIOUS_GENERATION_PREPARED: actual native progress, active clock, answers and sold pending seat")
else:
    before = json.loads(params.get_str(key + ".snapshot"))
    after = snapshot()
    # Schema may add columns, but no old column or old row may change on update.
    for table, rows in before.items():
        if table == "file_bytes":
            assert after[table] == rows
            continue
        assert len(after[table]) == len(rows), table
        for old, new in zip(rows, after[table]):
            assert {name: new[name] for name in old} == old, (table, old["id"])
    data = json.loads(saved)
    line = env["sale.order.line"].with_user(data["manager"]).browse(data["line"])
    assert not line.learning_plan, "Old sale was backfilled during module update"
    slide = env["slide.slide"].with_user(data["author"]).browse(data["slide"])
    exam = slide.survey_id
    next_version = env["survey.survey"].with_user(data["author"]).browse(exam.action_mock_new_version()["res_id"])
    next_version.write({"training_version": "next", "training_revision_reason": "Fictional post-upgrade revision"})
    next_version.action_mock_publish()
    env["training.elearning.exam.revision"].with_user(data["author"]).create(
        {
            "slide_id": slide.id,
            "exam_id": next_version.id,
            "reason": "Fictional explicit revision after verified upgrade",
        }
    ).action_apply()
    assert line.learning_plan["slides"][1]["exam"] == exam.id
    attempt = env["survey.user_input"].browse(data["attempt"])
    deadline = attempt.deadline
    resumed = env["training.elearning.exam.service"].with_user(data["learner"])._start(data["member"], slide.id)
    assert resumed.id == attempt.id and resumed.deadline == deadline
    pending = env["training.elearning.sale.allocation"].with_user(data["manager"]).browse(data["pending"])
    pending.action_learning_activate()
    started = env["training.elearning.exam.service"].with_user(data["later"])._start(pending.membership_id.id, slide.id)
    assert started.survey_id == exam
    print(
        "GENERATION_UPGRADE_PRESERVED: every old column/byte; explicit revision preserves active attempt and older sold obligation"
    )
