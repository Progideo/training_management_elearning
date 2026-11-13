# ruff: noqa: F821  # Odoo shell supplies env
"""Retained closed and live purchase summaries on one native membership."""

import json
from datetime import timedelta
from unittest.mock import patch
from odoo import Command, fields
from odoo.tests import new_test_user

assert env.cr.dbname == "tm_suite_test"
params = env["ir.config_parameter"]
key = "autonomous.purchase.reports.retained"
saved = params.get_str(key)
if not saved:
    manager = new_test_user(
        env,
        login="fictional_retained_report_coordinator",
        groups="training_elearning_sale.group_learning_sales_manager",
    )
    learner = new_test_user(env, login="fictional_retained_report_learner", groups="base.group_portal")
    buyer = env["res.partner"].create({"name": "Fictional retained report buyer"})
    catalog = env["training.course"].create({"name": "Fictional retained report catalogue"})
    course = (
        env["slide.channel"]
        .with_user(manager)
        .create({"name": "Fictional retained report edition", "training_course_id": catalog.id})
    )
    slide = (
        env["slide.slide"]
        .with_user(manager)
        .create(
            {
                "channel_id": course.id,
                "name": "Fictional retained article",
                "slide_category": "article",
                "html_content": "<p>PRIVATE RETAINED REPORT ARTICLE</p>",
                "is_published": True,
            }
        )
    )
    course.action_learning_publish()
    seats = env["training.elearning.sale.allocation"]
    for months in (1, 6):
        product = (
            env["product.product"]
            .with_user(manager)
            .create(
                {
                    "name": "Fictional retained report offer",
                    "type": "service",
                    "learning_channel_id": course.id,
                    "learning_access_months": months,
                }
            )
        )
        order = (
            env["sale.order"]
            .with_user(manager)
            .create(
                {
                    "partner_id": buyer.id,
                    "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 1})],
                }
            )
        )
        order.action_confirm()
        order.order_line.action_learning_authorize("Fictional retained funding authorization")
        seat = (
            env["training.elearning.sale.allocation"]
            .with_user(manager)
            .create(
                {
                    "line_id": order.order_line.id,
                    "partner_id": learner.partner_id.id,
                }
            )
        )
        seat.action_learning_activate()
        seats |= seat
    member = seats.membership_id
    assert len(member) == 1
    with patch.object(fields.Datetime, "now", return_value=seats[0].access_ends_at + timedelta(days=1)):
        env["training.elearning.service"].with_user(learner)._declare(member.id, slide.id)
        assert seats[0]._purchase_summary()["percentage"] == 0
        assert seats[1]._purchase_summary()["percentage"] == 100
    report_ids = seats.report_course_ids.ids
    evidence_ids = (
        env["slide.slide.partner"].search([("slide_id", "=", slide.id), ("partner_id", "=", learner.partner_id.id)]).ids
    )
    env.flush_all()
    saved = {"reports": report_ids, "evidence": evidence_ids}
    for table, ids in (("training_elearning_sale_course_report", report_ids), ("slide_slide_partner", evidence_ids)):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE id = ANY(%s) ORDER BY id", [ids])
        saved[table] = [row[0] for row in env.cr.fetchall()]
    params.set_str(key, json.dumps(saved, default=str, sort_keys=True))
    env.cr.commit()
else:
    saved = json.loads(saved)
    for table, ids in (
        ("training_elearning_sale_course_report", saved["reports"]),
        ("slide_slide_partner", saved["evidence"]),
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE id = ANY(%s) ORDER BY id", [ids])
        assert [row[0] for row in env.cr.fetchall()] == saved[table]
    reports = env["training.elearning.sale.course.report"].browse(saved["reports"])
    assert reports[0].snapshot["percentage"] == 0
    assert reports[0].closed_at
    assert not reports[1].closed_at
print("Purchase summary snapshots, own periods and first native acquisition timestamps preserved")
