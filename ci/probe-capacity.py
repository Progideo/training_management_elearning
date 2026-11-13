# ruff: noqa: F821  # Odoo shell supplies env
"""One seat remains one seat even when a transaction predates a committed reservation."""

from psycopg2.errors import SerializationFailure
from odoo import api, Command
from odoo.exceptions import LockError, ValidationError
from odoo.tests import new_test_user

assert env.cr.dbname == "tm_suite_test"
manager = new_test_user(
    env, login="fictional_stale_capacity_manager", groups="training_elearning_sale.group_learning_sales_manager"
)
first_learner = new_test_user(env, login="fictional_stale_capacity_first", groups="base.group_portal")
second_learner = new_test_user(env, login="fictional_stale_capacity_second", groups="base.group_portal")
catalog = env["training.course"].create({"name": "Fictional stale capacity catalogue"})
course = (
    env["slide.channel"]
    .with_user(manager)
    .create({"name": "Fictional stale capacity edition", "training_course_id": catalog.id})
)
env["slide.slide"].with_user(manager).create(
    {
        "name": "Fictional stale capacity article",
        "channel_id": course.id,
        "slide_category": "article",
        "html_content": "<p>Fictional stale capacity content</p>",
        "is_published": True,
    }
)
course.action_learning_publish()
product = (
    env["product.product"]
    .with_user(manager)
    .create({"name": "Fictional final seat offer", "type": "service", "learning_channel_id": course.id})
)
buyer = env["res.partner"].create({"name": "Fictional concurrent seat buyer"})
order = (
    env["sale.order"]
    .with_user(manager)
    .create({"partner_id": buyer.id, "order_line": [Command.create({"product_id": product.id, "product_uom_qty": 1})]})
)
order.action_confirm()
line = order.order_line
line_id, actor_id = line.id, manager.id
first_partner, second_partner = first_learner.partner_id.id, second_learner.partner_id.id
context = {"allowed_company_ids": env.company.ids}
env.cr.commit()
with env.registry.cursor() as stale, env.registry.cursor() as winner:
    stale.execute("SHOW transaction_isolation")
    assert stale.fetchone()[0] == "repeatable read"
    old_line = api.Environment(stale, actor_id, context)["sale.order.line"].browse(line_id)
    assert old_line.product_uom_qty == 1
    seat = api.Environment(winner, actor_id, context)["training.elearning.sale.allocation"].create(
        {"line_id": line_id, "partner_id": first_partner}
    )
    winner.commit()
    try:
        api.Environment(stale, actor_id, context)["training.elearning.sale.allocation"].create(
            {"line_id": line_id, "partner_id": second_partner}
        )
    except (SerializationFailure, LockError):
        pass
    else:
        raise AssertionError("Stale snapshot reserved the already committed final seat")
    stale.rollback()
with env.registry.cursor() as retry:
    try:
        api.Environment(retry, actor_id, context)["training.elearning.sale.allocation"].create(
            {"line_id": line_id, "partner_id": second_partner}
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("A fresh retry exceeded the sold capacity")
env.cr.rollback()
env.invalidate_all()
assert env["training.elearning.sale.allocation"].search_count([("line_id", "=", line_id)]) == 1
assert line.learning_allocation_revision == 1
print("STALE_CAPACITY_PRESERVED: prior Repeatable Read snapshot must retry; fresh retry cannot exceed the final seat")
