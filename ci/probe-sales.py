# ruff: noqa: F821  # Odoo shell supplies env
"""Real retained sales and independent seat/activation transactions; fictitious DB only."""

import json
from odoo import api
from odoo.exceptions import LockError, ValidationError
from odoo.tests import new_test_user

assert env.cr.dbname == "tm_suite_test"
assert not any(
    n.startswith("training_management")
    for n in env["ir.module.module"].search([("state", "=", "installed")]).mapped("name")
)
params = env["ir.config_parameter"]
key = "autonomous.sales.retained"
saved = params.get_str(key)


def snapshot():
    env.flush_all()
    result = {}
    for table in (
        "sale_order_line",
        "training_elearning_sale_allocation",
        "slide_channel_partner",
        "survey_user_input",
        "survey_user_input_line",
        "training_elearning_exam_requirement",
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id")
        result[table] = [r[0] for r in env.cr.fetchall()]
    return json.dumps(result, sort_keys=True, default=str)


if saved:
    assert snapshot() == params.get_str(key + ".snapshot"), "Sales or exam evidence changed during update"
    print("AUTONOMOUS_SALES_PRESERVED: native lines, frozen conditions, grants, obligations, answers and deadlines")
else:
    retained = json.loads(params.get_str("autonomous.retained.native.evidence"))
    member = env["slide.channel.partner"].browse(retained["member"])
    manager = new_test_user(
        env, login="fictional_sales_upgrade_coordinator", groups="training_elearning_sale.group_learning_sales_manager"
    )
    learner = member.learning_user_id
    buyer = env["res.partner"].create({"name": "Fictional retained buyer"})
    product = (
        env["product.product"]
        .with_user(manager)
        .create({"name": "Fictional retained seat", "type": "service", "learning_channel_id": member.channel_id.id})
    )
    order = env["sale.order"].with_user(manager).create({"partner_id": buyer.id})
    line = (
        env["sale.order.line"]
        .with_user(manager)
        .create(
            {"order_id": order.id, "product_id": product.id, "product_uom_qty": 1, "learning_purchase_kind": "renewal"}
        )
    )
    order.action_confirm()
    line.action_learning_authorize("Fictional retained commercial decision")
    seat = (
        env["training.elearning.sale.allocation"]
        .with_user(manager)
        .create({"line_id": line.id, "partner_id": learner.partner_id.id})
    )
    seat.action_learning_activate()
    assert seat.membership_id == member
    # A second confirmed line with one seat is contested by two separate transactions.
    contested_order = env["sale.order"].with_user(manager).create({"partner_id": buyer.id})
    contested = (
        env["sale.order.line"]
        .with_user(manager)
        .create({"order_id": contested_order.id, "product_id": product.id, "product_uom_qty": 1})
    )
    contested_order.action_confirm()
    contested.action_learning_authorize("Fictional concurrent commercial decision")
    partners = [
        new_test_user(env, login=f"fictional_contested_{i}", groups="base.group_portal").partner_id.id for i in range(2)
    ]
    manager_id, line_id = manager.id, contested.id
    context = {"allowed_company_ids": member.channel_id.learning_company_id.ids}
    env.cr.commit()
    with env.registry.cursor() as first, env.registry.cursor() as second:
        one, two = [
            api.Environment(cr, manager_id, context)["training.elearning.sale.allocation"] for cr in (first, second)
        ]
        allocated = one.create({"line_id": line_id, "partner_id": partners[0]})
        allocated_id = allocated.id
        try:
            two.create({"line_id": line_id, "partner_id": partners[1]})
        except LockError:
            pass
        else:
            raise AssertionError("Seat allocation ignored held native line lock")
        first.commit()
        second.rollback()
    with env.registry.cursor() as retry:
        allocation = api.Environment(retry, manager_id, context)["training.elearning.sale.allocation"]
        try:
            allocation.create({"line_id": line_id, "partner_id": partners[1]})
        except ValidationError:
            pass
        else:
            raise AssertionError("Retry overbooked the one-seat line")
    with env.registry.cursor() as first, env.registry.cursor() as second:
        one, two = [
            api.Environment(cr, manager_id, context)["training.elearning.sale.allocation"].browse(allocated_id)
            for cr in (first, second)
        ]
        one.action_learning_activate()
        end = one.access_ends_at
        mail = one.notification_mail_id.id
        try:
            two.action_learning_activate()
        except LockError:
            pass
        else:
            raise AssertionError("Activation ignored held native line lock")
        first.commit()
        second.rollback()
    with env.registry.cursor() as retry:
        repeated = api.Environment(retry, manager_id, context)["training.elearning.sale.allocation"].browse(
            allocated_id
        )
        repeated.action_learning_activate()
        assert repeated.access_ends_at == end and repeated.notification_mail_id.id == mail
        retry.commit()
    env.cr.rollback()
    env.invalidate_all()
    params.set_str(key, json.dumps({"seat": seat.id, "contested": allocated_id}))
    params.set_str(key + ".snapshot", snapshot())
    env.cr.commit()
    print("AUTONOMOUS_SALES_PREPARED: retained renewal; competing allocations and repeated activation serialized")
