# ruff: noqa: F821  # Odoo shell supplies env
"""Retained human evidence and concurrent reassignment; no mail transport is called."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4
from odoo import api, fields, Command
from odoo.exceptions import AccessError, LockError
from odoo.tests import new_test_user

assert env.cr.dbname == "tm_suite_test"
params = env["ir.config_parameter"]
key = "autonomous.human.practical.retained"
saved = params.get_str(key)
if not saved:
    manager = new_test_user(
        env, login="fictional_retained_human_manager", groups="training_elearning.group_elearning_pedagogy_manager"
    )
    learner = new_test_user(env, login="fictional_retained_human_learner", groups="base.group_portal")
    reviewers = [
        new_test_user(
            env, login=f"fictional_retained_human_reviewer_{i}", groups="training_elearning.group_elearning_reviewer"
        )
        for i in range(2)
    ]
    catalog = env["training.course"].create({"name": "Fictional retained human catalogue"})
    course = (
        env["slide.channel"]
        .with_user(manager)
        .create(
            {
                "name": "Fictional retained human edition",
                "training_course_id": catalog.id,
                "learning_reviewer_id": reviewers[0].id,
            }
        )
    )
    task = (
        env["training.elearning.practical"]
        .with_user(manager)
        .create(
            {
                "name": "Fictional retained human instructions",
                "training_course_id": catalog.id,
                "criterion": "human",
                "instructions": "Fictional retained instructions",
                "rubric_ids": [Command.create({"description": "Fictional retained rubric criterion"})],
            }
        )
    )
    task.action_publish()
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
        fields.Datetime.now() + timedelta(days=2), learner.id, "Fictional retained human grant"
    )
    row = (
        env["training.elearning.practical.service"]
        .with_user(learner)
        ._deposit(member.id, slide.id, [("fictional.txt", b"PRIVATE RETAINED HUMAN WORK")], str(uuid4()))
    )
    queue = row.review_queue_id
    context = {"allowed_company_ids": course.learning_company_id.ids}
    queue_id, row_id, manager_id, old_id, new_id = queue.id, row.id, manager.id, reviewers[0].id, reviewers[1].id
    results = {str(line.id): False for line in task.rubric_ids}
    due_at = queue.due_at
    env.cr.commit()
    with env.registry.cursor() as first, env.registry.cursor() as second:
        one = api.Environment(first, manager_id, context)["training.elearning.review.queue"].browse(queue_id)
        two = api.Environment(second, old_id, context)["training.elearning.review.queue"].browse(queue_id)
        one._reassign(one.env["res.users"].browse(new_id), "Fictional concurrent reviewer change")
        try:
            two._publish(row_id, "revision", results, "Fictional stale reviewer feedback")
        except LockError:
            pass
        else:
            raise AssertionError("Concurrent publication ignored the held reassignment locks")
        first.commit()
        second.rollback()
    with env.registry.cursor() as retry:
        stale = api.Environment(retry, old_id, context)["training.elearning.review.queue"].browse(queue_id)
        try:
            stale._publish(row_id, "revision", results, "Fictional revoked reviewer feedback")
        except AccessError:
            pass
        else:
            raise AssertionError("Former reviewer retained publication rights after reassignment")
    with env.registry.cursor() as current:
        live = api.Environment(current, new_id, context)["training.elearning.review.queue"].browse(queue_id)
        live._publish(row_id, "revision", results, "PRIVATE RETAINED HUMAN FEEDBACK")
        current.commit()
    env.cr.rollback()
    env.invalidate_all()
    assert queue.due_at == due_at and member.completion == 0
    assert row.review_id.reviewer_id.id == new_id and not queue.revision_until
    fixture = {
        "course": course.id,
        "slide": slide.id,
        "member": member.id,
        "task": task.id,
        "queue": queue.id,
        "row": row.id,
        "payload": row.payload_id.id,
        "files": row.payload_id.file_ids.ids,
        "review": row.review_id.id,
        "calendar": course.learning_review_calendar_id.id,
        "resource": course.learning_review_calendar_id.learning_review_resource_id.id,
    }
    params.set_str(key, json.dumps(fixture))
else:
    fixture = json.loads(saved)


def snapshot():
    env.flush_all()
    result = {}
    notices = env["training.elearning.review.notice"].search([("queue_id", "=", fixture["queue"])])
    for table, column, ids in (
        ("slide_channel", "id", [fixture["course"]]),
        ("slide_slide", "id", [fixture["slide"]]),
        ("slide_channel_partner", "id", [fixture["member"]]),
        ("slide_slide_partner", "slide_id", [fixture["slide"]]),
        ("training_elearning_practical", "id", [fixture["task"]]),
        ("training_elearning_practical_rubric", "practical_id", [fixture["task"]]),
        ("training_elearning_submission", "id", [fixture["row"]]),
        ("training_elearning_submission_payload", "id", [fixture["payload"]]),
        ("learning_submission_file_rel", "payload_id", [fixture["payload"]]),
        ("training_elearning_review_queue", "id", [fixture["queue"]]),
        ("training_elearning_review", "id", [fixture["review"]]),
        ("training_elearning_review_notice", "queue_id", [fixture["queue"]]),
        ("resource_calendar", "id", [fixture["calendar"]]),
        ("resource_calendar_attendance", "calendar_id", [fixture["calendar"]]),
        ("resource_calendar_leaves", "calendar_id", [fixture["calendar"]]),
        ("resource_resource", "id", [fixture["resource"]]),
        ("ir_attachment", "id", fixture["files"]),
        ("mail_mail", "id", notices.mail_id.ids),
        ("mail_message", "id", notices.mail_id.mail_message_id.ids),
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE {column} = ANY(%s) ORDER BY to_jsonb(t)::text", [ids])
        result[table] = [row[0] for row in env.cr.fetchall()]
    result["mail_recipients"] = {str(mail.id): sorted(mail.recipient_ids.ids) for mail in notices.mail_id}
    result["file_hashes"] = {
        str(file.id): hashlib.sha256(file.raw.content).hexdigest()
        for file in env["ir.attachment"].browse(fixture["files"])
    }
    return json.dumps(result, sort_keys=True, default=str)


old = params.get_str(key + ".snapshot")
if old:
    assert snapshot() == old, (
        "Human practical contracts, judgements, deadlines, private bytes or native mails changed during update"
    )
    print(
        "HUMAN_PRACTICALS_PRESERVED: calendar, rubric, immutable feedback, native progress, dates and exact file hashes"
    )
else:
    params.set_str(key + ".snapshot", snapshot())
    env.cr.commit()
    print(
        "HUMAN_PRACTICALS_PREPARED: concurrent reassignment revoked stale reviewer; current judgement retained; no SMTP called"
    )
