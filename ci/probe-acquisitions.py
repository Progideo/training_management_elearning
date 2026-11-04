# ruff: noqa: F821 -- the native Odoo shell provides env.
"""Actual transaction contention and retained invalidation evidence after update."""

import json
from datetime import timedelta
from uuid import uuid4
from odoo import api, fields
from odoo.exceptions import LockError
from odoo.tests import new_test_user
from psycopg2.errors import SerializationFailure

assert env.cr.dbname == "tm_suite_test"
params = env["ir.config_parameter"]
key = "autonomous.acquisition.retained"
saved = params.get_str(key)


def snapshot(member, slide_id):
    env.flush_all()
    result = {}
    for table, domain, args in (
        ("slide_channel_partner", "id=%s", [member.id]),
        ("slide_slide_partner", "slide_id=%s AND partner_id=%s", [slide_id, member.partner_id.id]),
        ("training_elearning_acquisition_invalidation", "membership_id=%s", [member.id]),
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE {domain} ORDER BY id", args)
        result[table] = [row[0] for row in env.cr.fetchall()]
    return json.dumps(result, sort_keys=True, default=str)


if not saved:
    manager = new_test_user(
        env,
        login="fictional_retained_acquisition_coordinator",
        groups="training_elearning.group_elearning_pedagogy_manager",
    )
    learner = new_test_user(env, login="fictional_retained_acquisition_learner", groups="base.group_portal")
    catalog = env["training.course"].create({"name": "Fictional retained acquisition catalogue"})
    course = (
        env["slide.channel"]
        .with_user(manager)
        .create({"name": "Fictional retained acquisition edition", "training_course_id": catalog.id})
    )
    slide = (
        env["slide.slide"]
        .with_user(manager)
        .create(
            {
                "name": "Fictional retained acquisition article",
                "channel_id": course.id,
                "slide_category": "article",
                "html_content": "<p>Fictional retained private content</p>",
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
    member.action_learning_activate(fields.Datetime.now() + timedelta(days=2), learner.id, "Fictional controlled grant")
    env["training.elearning.service"].with_user(learner)._declare(member.id, slide.id)
    member_id, slide_id, manager_id = member.id, slide.id, manager.id
    request_key = str(uuid4())
    env.cr.commit()
    with env.registry.cursor() as winning_cr, env.registry.cursor() as old_cr:
        winning = api.Environment(winning_cr, manager_id, {})
        old = api.Environment(old_cr, manager_id, {})
        old_member = old["slide.channel.partner"].browse(member_id)
        old_member.read(["completion"])
        winner = winning["training.elearning.acquisition.invalidation"]._invalidate(
            winning["slide.channel.partner"].browse(member_id),
            slide_id,
            "Fictional contended acquisition decision",
            request_key,
        )
        winner_id = winner.id
        try:
            old["training.elearning.acquisition.invalidation"]._invalidate(
                old_member, slide_id, "Fictional contended acquisition decision", request_key
            )
        except LockError:
            print("J18_HELD_ACQUISITION_REFUSED")
        else:
            raise AssertionError("A held acquisition was not protected")
        winning_cr.commit()
        try:
            old["training.elearning.acquisition.invalidation"]._invalidate(
                old_member, slide_id, "Fictional contended acquisition decision", request_key
            )
        except (LockError, SerializationFailure):
            print("J18_STALE_ACQUISITION_REFUSED")
        else:
            raise AssertionError("A stale acquisition snapshot was not rejected")
        old_cr.rollback()
    with env.registry.cursor() as retry_cr:
        retry = api.Environment(retry_cr, manager_id, {})
        same = retry["training.elearning.acquisition.invalidation"]._invalidate(
            retry["slide.channel.partner"].browse(member_id),
            slide_id,
            "Fictional contended acquisition decision",
            request_key,
        )
        assert same.id == winner_id
        assert (
            retry["training.elearning.acquisition.invalidation"].search_count([("membership_id", "=", member_id)]) == 1
        )
        retry_cr.commit()
    env.cr.rollback()
    env.invalidate_all()
    member = env["slide.channel.partner"].browse(member_id)
    assert member.completion == 0
    leaf = env["slide.slide.partner"].search([("slide_id", "=", slide_id), ("partner_id", "=", member.partner_id.id)])
    assert not leaf.completed and leaf.learning_completed_at and leaf.learning_valid_completed_at
    params.set_str(key, json.dumps({"member": member_id, "slide": slide_id, "snapshot": snapshot(member, slide_id)}))
    env.cr.commit()
    print("J18_RETRY_SAME_DECISION_NATIVE_FIRST_ACQUISITION_AND_RIGHTS_RETAINED")
else:
    data = json.loads(saved)
    assert snapshot(env["slide.channel.partner"].browse(data["member"]), data["slide"]) == data["snapshot"]
    print("J18_NATIVE_INVALIDATION_RIGHTS_AND_ORIGINAL_PROOFS_PRESERVED")
