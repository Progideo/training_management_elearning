# ruff: noqa: F821  # Odoo shell supplies env
"""Retain real formative events/native acquisition; contend on first-class member locks."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4
from odoo import api, fields
from odoo.exceptions import LockError
from odoo.tests import new_test_user
from psycopg2.errors import SerializationFailure
from odoo.addons.training_interactive.tests.test_library import package

assert env.cr.dbname == "tm_suite_test"
params = env["ir.config_parameter"]
key = "autonomous.interactive.lessons.retained"
saved = params.get_str(key)
if not saved:
    manager = new_test_user(
        env, login="fictional_retained_interactive_coordinator", groups="training_elearning.group_elearning_manager"
    )
    learner = new_test_user(env, login="fictional_retained_interactive_learner", groups="base.group_portal")
    resource = (
        env["training.elearning.resource"]
        .with_user(manager)
        .create({"name": "Fictional retained shared resource", "format": "scorm12"})
    )
    version = (
        env["training.elearning.version"]
        .with_user(manager)
        ._import(resource, "1", package(), "Fictional licence", "Fictional retained source")
    )
    version.action_publish()
    catalog = env["training.course"].create({"name": "Fictional retained interactive catalogue"})
    course = (
        env["slide.channel"]
        .with_user(manager)
        .create({"name": "Fictional retained interactive course", "training_course_id": catalog.id})
    )
    slide = (
        env["slide.slide"]
        .with_user(manager)
        .create(
            {
                "channel_id": course.id,
                "learning_interactive_version_id": version.id,
                "learning_interactive_rule": "score",
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
    member.action_learning_activate(
        fields.Datetime.now() + timedelta(days=2), learner.id, "Fictional retained interactive grant"
    )
    model = env["training.elearning.interactive.attempt"].with_user(learner)
    first = model._start(member.id, slide.id, str(uuid4()))
    first._save(
        "retained-pass",
        1,
        {
            "state": {"private": "RETAINED INTERACTIVE RESUME"},
            "result": {"score": 90, "maximum": 100, "completed": True},
        },
    )
    acquired = member.completion_date
    second = model._start(member.id, slide.id, str(uuid4()), new=True)
    second._save("retained-lower-score", 1, {"result": {"score": 10, "maximum": 100, "completed": True}})
    assert member.completion == 100 and member.completion_date == acquired
    actor, member_id, slide_id = learner.id, member.id, slide.id
    context = {"allowed_company_ids": course.learning_company_id.ids}
    request_key = str(uuid4())
    env.cr.commit()
    with env.registry.cursor() as winner, env.registry.cursor() as old, env.registry.cursor() as held:
        stale = api.Environment(old, actor, context)["training.elearning.interactive.attempt"]
        assert stale.sudo().search_count([("membership_id", "=", member_id)]) == 2
        third = api.Environment(winner, actor, context)["training.elearning.interactive.attempt"]._start(
            member_id, slide_id, request_key, new=True
        )
        third_id = third.id
        try:
            api.Environment(held, actor, context)["training.elearning.interactive.attempt"]._start(
                member_id, slide_id, str(uuid4()), new=True
            )
        except LockError:
            pass
        else:
            raise AssertionError("Concurrent interactive launch ignored the held source lock")
        held.rollback()
        winner.commit()
        try:
            stale._start(member_id, slide_id, str(uuid4()), new=True)
        except (LockError, SerializationFailure):
            pass
        else:
            raise AssertionError("Stale interactive launch ignored the committed member revision")
        old.rollback()
    with env.registry.cursor() as retry:
        repeated = api.Environment(retry, actor, context)["training.elearning.interactive.attempt"]._start(
            member_id, slide_id, request_key, new=True
        )
        assert repeated.id == third_id and repeated.number == 3
        retry.rollback()
    env.cr.rollback()
    env.invalidate_all()
    attempts = env["training.elearning.interactive.attempt"].search([("membership_id", "=", member_id)], order="number")
    events = env["training.elearning.interactive.event"].search([("attempt_id", "in", attempts.ids)])
    evidence = env["slide.slide.partner"].search(
        [("slide_id", "=", slide_id), ("partner_id", "=", learner.partner_id.id)]
    )
    assert member.completion == 100 and member.completion_date == acquired
    env.flush_all()
    saved = {
        "member": member_id,
        "files": {str(file.id): hashlib.sha256(file.data.content).hexdigest() for file in version.sudo().file_ids},
    }
    for table, ids in (
        ("training_elearning_interactive_attempt", attempts.ids),
        ("training_elearning_interactive_event", events.ids),
        ("slide_channel_partner", [member_id]),
        ("slide_slide_partner", evidence.ids),
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE id = ANY(%s) ORDER BY id", [ids])
        saved[table] = {"ids": ids, "rows": [row[0] for row in env.cr.fetchall()]}
    params.set_str(key, json.dumps(saved, sort_keys=True))
    env.cr.commit()
else:
    saved = json.loads(saved)
    for table in (
        "training_elearning_interactive_attempt",
        "training_elearning_interactive_event",
        "slide_channel_partner",
        "slide_slide_partner",
    ):
        data = saved[table]
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE id = ANY(%s) ORDER BY id", [data["ids"]])
        assert [row[0] for row in env.cr.fetchall()] == data["rows"]
    for file_id, digest in saved["files"].items():
        assert hashlib.sha256(env["training.elearning.file"].browse(int(file_id)).data.content).hexdigest() == digest
    assert env["slide.channel.partner"].browse(saved["member"]).completion == 100
print("Shared package bytes, formative states/events, first native acquisition and concurrent launch replay preserved")
