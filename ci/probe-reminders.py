# ruff: noqa: F821 -- native Odoo shell supplies env.
"""Retain future schedules, queued envelopes and their native identities after update."""

import json
from datetime import timedelta
from odoo import api, fields
from odoo.tests import new_test_user

assert env.cr.dbname == "tm_suite_test"
params = env["ir.config_parameter"]
key = "autonomous.scoped.reminders.retained"
saved = params.get_str(key)
if not saved:
    manager = new_test_user(
        env,
        login="fictional_retained_reminder_coordinator",
        groups="training_elearning.group_elearning_pedagogy_manager",
    )
    learner = new_test_user(env, login="fictional_retained_reminder_learner", groups="base.group_portal")
    catalog = env["training.course"].create({"name": "Fictional retained reminder catalogue"})
    course = (
        env["slide.channel"]
        .with_user(manager)
        .create({"name": "Fictional retained reminder course", "training_course_id": catalog.id})
    )
    env["slide.slide"].with_user(manager).create(
        {
            "name": "Fictional retained reminder article",
            "channel_id": course.id,
            "slide_category": "article",
            "html_content": "<p>Fictional private retained article</p>",
            "is_published": True,
        }
    )
    course.action_learning_publish()
    member = (
        env["slide.channel.partner"]
        .with_user(manager)
        .create({"channel_id": course.id, "partner_id": learner.partner_id.id})
    )
    company = env.company.with_user(env.ref("base.user_admin"))
    policy = company.read(["learning_notice_long_days", "learning_notice_short_days"])[0]
    company.write({"learning_notice_long_days": 0, "learning_notice_short_days": 0})
    # A template update must also validate against an older event whose target
    # became obsolete after a second grant, without changing its retained mail.
    earlier_learner = new_test_user(env, login="fictional_retained_obsolete_learner", groups="base.group_portal")
    earlier_member = env["slide.channel.partner"].with_user(manager).create(
        {"channel_id": course.id, "partner_id": earlier_learner.partner_id.id}
    )
    earlier_member.action_learning_activate(
        fields.Datetime.now() + timedelta(days=30), earlier_learner.id, "Fictional first retained grant"
    )
    obsolete = env["training.elearning.reminder"].search(
        [("membership_id", "=", earlier_member.id), ("kind", "=", "activation")]
    )
    earlier_member.action_learning_activate(
        fields.Datetime.now() + timedelta(days=60), earlier_learner.id, "Fictional second retained grant"
    )
    assert len(obsolete) == 1 and not obsolete._target()
    assert not obsolete.mail_id._learning_delivery_allowed() and obsolete.state == "cancelled"
    member.action_learning_activate(
        fields.Datetime.now() + timedelta(days=60), learner.id, "Fictional retained notice grant"
    )
    company.write({name: policy[name] for name in ("learning_notice_long_days", "learning_notice_short_days")})
    member_id = member.id
    env.cr.commit()
    with env.registry.cursor() as winning_cr, env.registry.cursor() as old_cr:
        winning = api.Environment(winning_cr, manager.id, {})
        old = api.Environment(old_cr, manager.id, {})
        assert (
            old["training.elearning.reminder"].search_count(
                [("membership_id", "=", member_id), ("kind", "=", "course_end")]
            )
            == 0
        )
        winner = winning["training.elearning.reminder"]._enqueue(
            "course_end", winning["slide.channel.partner"].browse(member_id), offset=policy["learning_notice_long_days"]
        )
        winner_id = winner.id
        winning_cr.commit()
        # RR cannot see the newly committed event, while the unique index can.
        same = old["training.elearning.reminder"]._enqueue(
            "course_end", old["slide.channel.partner"].browse(member_id), offset=policy["learning_notice_long_days"]
        )
        assert not same
        old_cr.execute("SELECT 1")
        assert old_cr.fetchone() == (1,)
        old_cr.commit()
    env.cr.rollback()
    env.invalidate_all()
    assert (
        env["training.elearning.reminder"]._enqueue("course_end", member, offset=policy["learning_notice_long_days"]).id
        == winner_id
    )
    env["training.elearning.reminder"]._enqueue("course_end", member, offset=policy["learning_notice_short_days"])
    print("J19_CONTENDED_SCHEDULE_SINGLE_EVENT_AND_BUSINESS_TRANSACTION_RETAINED")
    notices = env["training.elearning.reminder"].sudo().search([("membership_id", "=", member.id)])
    assert len(notices.filtered(lambda notice: notice.kind == "activation" and notice.state == "queued")) == 1
    assert len(notices.filtered(lambda notice: notice.kind == "course_end" and notice.state == "pending")) == 2
    assert all(notice._allowed() for notice in notices)
    retained = notices | env["training.elearning.reminder"].search([("membership_id", "=", earlier_member.id)])
    data = {"member": member.id, "earlier_member": earlier_member.id, "obsolete": obsolete.id,
            "notices": retained.ids, "mails": retained.mail_id.ids}
else:
    data = json.loads(saved)


def snapshot():
    env.flush_all()
    result = {}
    for table, ids in (
        ("training_elearning_reminder", data["notices"]),
        ("mail_mail", data["mails"]),
        ("slide_channel_partner", [data["member"], data["earlier_member"]]),
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE id=ANY(%s) ORDER BY id", [ids])
        result[table] = [row[0] for row in env.cr.fetchall()]
    mails = env["mail.mail"].sudo().browse(data["mails"])
    result["envelopes"] = [
        {
            "id": mail.id,
            "partners": mail.recipient_ids.ids,
            "email_to": mail.email_to,
            "email_cc": mail.email_cc,
            "attachments": mail.attachment_ids.ids,
            "body": str(mail.body_html),
        }
        for mail in mails
    ]
    return json.dumps(result, sort_keys=True, default=str)


if not saved:
    data["snapshot"] = snapshot()
    params.set_str(key, json.dumps(data))
    env.cr.commit()
    print("J19_FUTURE_REMINDERS_AND_NATIVE_ENVELOPES_PREPARED")
else:
    assert snapshot() == data["snapshot"]
    obsolete = env["training.elearning.reminder"].browse(data["obsolete"])
    assert obsolete.state == "cancelled" and not obsolete._target()
    print("J19_FUTURE_REMINDERS_AND_NATIVE_ENVELOPES_PRESERVED")
