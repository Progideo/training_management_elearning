# ruff: noqa: F821 -- native Odoo shell supplies env.
"""Two different courses contend for one native account of a checked contact."""

import json
from datetime import timedelta
from odoo import api, fields
from odoo.exceptions import LockError
from odoo.tests import new_test_user
from psycopg2.errors import SerializationFailure

assert env.cr.dbname == "tm_suite_test"
params = env["ir.config_parameter"]
key = "autonomous.native.invitation.retained"
saved = params.get_str(key)


def snapshot(data):
    env.flush_all()
    result = {}
    for table, ids in (
        ("slide_channel_partner", data["members"]),
        ("training_elearning_reminder", data["notices"]),
        ("mail_mail", data["mails"]),
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE id=ANY(%s) ORDER BY id", [ids])
        result[table] = [row[0] for row in env.cr.fetchall()]
    user = env["res.users"].sudo().browse(data["user"])
    result["account"] = user.read(["id", "partner_id", "login", "active", "company_id", "company_ids", "group_ids"])
    return json.dumps(result, sort_keys=True, default=str)


if not saved:
    manager = new_test_user(
        env, login="fictional_contended_native_inviter", groups="training_elearning.group_elearning_manager"
    )
    contact = env["res.partner"].create(
        {"name": "Fictional one invited contact", "email": "fictional.contended.invitation@example.invalid"}
    )
    catalog = env["training.course"].create({"name": "Fictional contended invitation catalogue"})
    members = []
    for number in (1, 2):
        course = (
            env["slide.channel"]
            .with_user(manager)
            .create({"name": "Fictional invitation edition %s" % number, "training_course_id": catalog.id})
        )
        env["slide.slide"].with_user(manager).create(
            {
                "name": "Fictional retained article",
                "channel_id": course.id,
                "slide_category": "article",
                "html_content": "<p>Fictional private content</p>",
                "is_published": True,
            }
        )
        course.action_learning_publish()
        members.append(
            env["slide.channel.partner"]
            .with_user(manager)
            .create({"channel_id": course.id, "partner_id": contact.id})
            .id
        )
    actor, partner_id = manager.id, contact.id
    end = fields.Datetime.now() + timedelta(days=2)
    env.cr.commit()
    with env.registry.cursor() as winning_cr, env.registry.cursor() as old_cr:
        winning = api.Environment(winning_cr, actor, {})
        old = api.Environment(old_cr, actor, {})
        assert not old["res.partner"].browse(partner_id).sudo().user_ids
        winning["slide.channel.partner"].browse(members[0]).action_learning_activate(
            end, reason="Fictional first native invitation"
        )
        try:
            old["slide.channel.partner"].browse(members[1]).action_learning_activate(
                end, reason="Fictional parallel native invitation"
            )
        except LockError:
            print("J20_NATIVE_CONTACT_INVITATION_LOCK_REFUSED")
        else:
            raise AssertionError("Two course grants ignored their shared contact lock")
        winning_cr.commit()
        try:
            old["slide.channel.partner"].browse(members[1]).action_learning_activate(
                end, reason="Fictional parallel native invitation"
            )
        except (LockError, SerializationFailure):
            print("J20_STALE_NATIVE_ACCOUNT_SNAPSHOT_REFUSED")
        else:
            raise AssertionError("An old account snapshot was not rejected")
        old_cr.rollback()
    with env.registry.cursor() as retry_cr:
        retry = api.Environment(retry_cr, actor, {})
        retry["slide.channel.partner"].browse(members[1]).action_learning_activate(
            end, reason="Fictional parallel native invitation"
        )
        retry_cr.commit()
    env.cr.rollback()
    env.invalidate_all()
    users = env["res.partner"].browse(partner_id).with_context(active_test=False).user_ids
    assert len(users) == 1
    contexts = env["slide.channel.partner"].browse(members)
    assert contexts.learning_user_id == users and all(contexts.mapped("learning_started_at"))
    notices = env["training.elearning.reminder"].sudo().search([("membership_id", "in", members)])
    assert len(notices.filtered(lambda notice: notice.kind == "invitation")) == 1
    assert all(notice.state == "queued" for notice in notices)
    data = {"members": members, "notices": notices.ids, "mails": notices.mail_id.ids, "user": users.id}
    data["snapshot"] = snapshot(data)
    params.set_str(key, json.dumps(data))
    env.cr.commit()
    print("J20_ONE_NATIVE_ACCOUNT_TWO_AUTHORIZED_CONTEXTS_ONE_INVITATION")
else:
    data = json.loads(saved)
    assert snapshot(data) == data["snapshot"]
    print("J20_NATIVE_ACCOUNT_GRANTS_AND_INVITATION_PRESERVED")
