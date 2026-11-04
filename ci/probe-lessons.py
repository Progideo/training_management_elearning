# ruff: noqa: F821  # Odoo shell supplies env
"""Native private article/PDF evidence survives update without optional apps."""

import hashlib
import io
import json
from datetime import timedelta
from odoo import api, fields
from odoo.exceptions import LockError
from odoo.tests import new_test_user
from odoo.tools import BinaryBytes
from odoo.tools.pdf import PdfFileWriter

assert env.cr.dbname == "tm_suite_test"
installed = env["ir.module.module"].search([("state", "=", "installed")]).mapped("name")
assert "training_elearning" in installed
assert not any(name.startswith("training_management") or name in ("sale", "survey") for name in installed), installed
params = env["ir.config_parameter"]
key = "autonomous.retained.lesson.evidence"
saved = params.get_str(key)
if not saved:
    manager = new_test_user(
        env, login="fictional_retained_lesson_manager", groups="training_elearning.group_elearning_manager"
    )
    learner = new_test_user(env, login="fictional_retained_lesson_learner", groups="base.group_portal")
    catalog = env["training.course"].create({"name": "Fictional retained lessons"})
    course = (
        env["slide.channel"]
        .with_user(manager)
        .create({"name": "Fictional retained native edition", "training_course_id": catalog.id})
    )
    article = (
        env["slide.slide"]
        .with_user(manager)
        .create(
            {
                "name": "Fictional retained article",
                "channel_id": course.id,
                "slide_category": "article",
                "html_content": "<p>Fictional retained private content</p>",
                "is_published": True,
            }
        )
    )
    output = io.BytesIO()
    writer = PdfFileWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(output)
    pdf = (
        env["slide.slide"]
        .with_user(manager)
        .create(
            {
                "name": "Fictional retained PDF",
                "channel_id": course.id,
                "slide_category": "document",
                "source_type": "local_file",
                "binary_content": BinaryBytes(output.getvalue()),
                "is_published": True,
            }
        )
    )
    course.action_learning_publish()
    member = (
        env["slide.channel.partner"]
        .with_user(manager)
        .create({"channel_id": course.id, "partner_id": learner.partner_id.id})
    )
    member.action_learning_activate(fields.Datetime.now() + timedelta(days=2), learner.id, "Fictional retained grant")
    env["training.elearning.service"].with_user(learner)._declare(member.id, article.id)
    assert member.completion == 50
    saved = json.dumps({"member": member.id, "slides": (article | pdf).ids, "course": course.id, "pdf": pdf.id})
    params.set_str(key, saved)
    learner_id, member_id, pdf_id = learner.id, member.id, pdf.id
    context = {"allowed_company_ids": env.company.ids}
    env.cr.commit()
    with env.registry.cursor() as first, env.registry.cursor() as second:
        api.Environment(first, learner_id, context)["training.elearning.service"]._declare(member_id, pdf_id)
        try:
            api.Environment(second, learner_id, context)["training.elearning.service"]._declare(member_id, pdf_id)
        except LockError:
            pass
        else:
            raise AssertionError("Repeated lesson declaration ignored the held grant lock")
        first.commit()
    with env.registry.cursor() as replay:
        api.Environment(replay, learner_id, context)["training.elearning.service"]._declare(member_id, pdf_id)
        replay.commit()
    env.cr.rollback()
    env.invalidate_all()
    assert member.completion == 100
    assert (
        env["slide.slide.partner"].search_count([("slide_id", "=", pdf_id), ("partner_id", "=", learner.partner_id.id)])
        == 1
    )

fixture = json.loads(saved)


def snapshot():
    env.flush_all()
    result = {}
    for table, domain, ids in (
        ("slide_channel", "id", [fixture["course"]]),
        ("slide_slide", "id", fixture["slides"]),
        ("slide_channel_partner", "id", [fixture["member"]]),
        ("slide_slide_partner", "slide_id", fixture["slides"]),
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE {domain} = ANY(%s) ORDER BY id", [ids])
        result[table] = [row[0] for row in env.cr.fetchall()]
    content = env["slide.slide"].browse(fixture["pdf"]).binary_content.content
    result["pdf_sha256"] = hashlib.sha256(content).hexdigest()
    return json.dumps(result, sort_keys=True, default=str)


old = params.get_str(key + ".snapshot")
if not old:
    params.set_str(key + ".snapshot", snapshot())
    env.cr.commit()
    print("LESSONS_PREPARED: native evidence, immutable plan and private PDF bytes")
else:
    assert snapshot() == old, "Native private lesson evidence changed during update"
    print("LESSONS_PRESERVED: exact native evidence, audit dates and PDF bytes")
