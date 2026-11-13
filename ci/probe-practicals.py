# ruff: noqa: F821  # Odoo shell supplies env
"""Retain actual private practical files and serialize repeated HTTP-style requests."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4
from odoo import api, fields
from odoo.exceptions import LockError
from odoo.tests import new_test_user

assert env.cr.dbname == "tm_suite_test"
params = env["ir.config_parameter"]
key = "autonomous.practical.retained"
saved = params.get_str(key)
if not saved:
    manager = new_test_user(
        env, login="fictional_retained_practical_manager", groups="training_elearning.group_elearning_manager"
    )
    learner = new_test_user(env, login="fictional_retained_practical_learner", groups="base.group_portal")
    catalog = env["training.course"].create({"name": "Fictional retained practical catalogue"})
    task = (
        env["training.elearning.practical"]
        .with_user(manager)
        .create(
            {
                "name": "Fictional retained private task",
                "training_course_id": catalog.id,
                "criterion": "deposit",
                "instructions": "Fictional retained instructions",
            }
        )
    )
    task.action_publish()
    course = (
        env["slide.channel"]
        .with_user(manager)
        .create({"name": "Fictional retained practical edition", "training_course_id": catalog.id})
    )
    slide = (
        env["slide.slide"]
        .with_user(manager)
        .create({"channel_id": course.id, "learning_practical_id": task.id, "is_published": True})
    )
    course.action_learning_publish()
    member = (
        env["slide.channel.partner"]
        .with_user(manager)
        .create({"channel_id": course.id, "partner_id": learner.partner_id.id})
    )
    member.action_learning_activate(
        fields.Datetime.now() + timedelta(days=2), learner.id, "Fictional retained practical grant"
    )
    member_id, slide_id, learner_id = member.id, slide.id, learner.id
    request_key = str(uuid4())
    files = [("fictional.txt", b"PRIVATE FICTIONAL RETAINED PRACTICAL")]
    context = {"allowed_company_ids": course.learning_company_id.ids}
    env.cr.commit()
    with env.registry.cursor() as first, env.registry.cursor() as second:
        one, two = [
            api.Environment(cr, learner_id, context)["training.elearning.practical.service"] for cr in (first, second)
        ]
        row = one._deposit(member_id, slide_id, files, request_key)
        row_id = row.id
        try:
            two._deposit(member_id, slide_id, files, request_key)
        except LockError:
            pass
        else:
            raise AssertionError("Repeated submission ignored the native grant lock")
        first.commit()
        second.rollback()
    with env.registry.cursor() as retry:
        repeated = api.Environment(retry, learner_id, context)["training.elearning.practical.service"]._deposit(
            member_id, slide_id, files, request_key
        )
        assert repeated.id == row_id
        retry.commit()
    env.cr.rollback()
    env.invalidate_all()
    rows = env["training.elearning.submission"].search([("membership_id", "=", member_id)])
    assert len(rows) == 1 and member.completion == 100
    fixture = {
        "course": course.id,
        "slide": slide_id,
        "task": task.id,
        "member": member_id,
        "row": row_id,
        "payload": rows.payload_id.id,
        "files": rows.payload_id.file_ids.ids,
    }
    params.set_str(key, json.dumps(fixture))
else:
    fixture = json.loads(saved)


def snapshot():
    env.flush_all()
    result = {}
    for table, column, ids in (
        ("training_elearning_practical", "id", [fixture["task"]]),
        ("training_elearning_submission", "id", [fixture["row"]]),
        ("training_elearning_submission_payload", "id", [fixture["payload"]]),
        ("learning_submission_file_rel", "payload_id", [fixture["payload"]]),
        ("slide_channel", "id", [fixture["course"]]),
        ("slide_slide", "id", [fixture["slide"]]),
        ("slide_channel_partner", "id", [fixture["member"]]),
        ("slide_slide_partner", "slide_id", [fixture["slide"]]),
        ("ir_attachment", "id", fixture["files"]),
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE {column} = ANY(%s) ORDER BY to_jsonb(t)::text", [ids])
        result[table] = [row[0] for row in env.cr.fetchall()]
    result["file_hashes"] = {
        str(file.id): hashlib.sha256(file.raw.content).hexdigest()
        for file in env["ir.attachment"].browse(fixture["files"])
    }
    return json.dumps(result, sort_keys=True, default=str)


old = params.get_str(key + ".snapshot")
if old:
    assert snapshot() == old, "Private practical versions, receipts, audit dates or bytes changed during update"
    print("PRACTICALS_PRESERVED: native progress, receipt, private bytes and immutable version")
else:
    params.set_str(key + ".snapshot", snapshot())
    env.cr.commit()
    print("PRACTICALS_PREPARED: real concurrent duplicate deposit serialized into one retained receipt")
