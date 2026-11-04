# ruff: noqa: F821  # Odoo shell supplies env
"""Retained mandate proofs, revocation/assignment contention and purchase isolation."""

import json
from datetime import timedelta
from odoo import api, fields, Command
from odoo.exceptions import AccessError, LockError
from odoo.tests import new_test_user

assert env.cr.dbname == "tm_suite_test"
params = env["ir.config_parameter"]
key = "autonomous.mandates.retained"
saved = params.get_str(key)


def snapshot():
    result = {}
    env.flush_all()
    for table in (
        "sale_order_line",
        "training_elearning_sale_allocation",
        "training_elearning_sale_mandate",
        "slide_channel_partner",
        "survey_user_input",
        "survey_user_input_line",
        "training_elearning_exam_requirement",
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id")
        result[table] = [r[0] for r in env.cr.fetchall()]
    return result


if saved:
    expected = json.loads(params.get_str(key + ".snapshot"))
    current = snapshot()
    for table, rows in expected.items():
        assert len(current[table]) == len(rows), (table, "Unexpected history creation or deletion")
        for before, after in zip(rows, current[table]):
            assert {k: after[k] for k in before} == before, (table, before["id"], "Prior value or audit date changed")
    data = json.loads(saved)
    user = env["res.users"].browse(data["user"])
    service = env["training.elearning.company.service"].with_user(user)
    try:
        service._view(data["revoked"])
    except AccessError:
        pass
    else:
        raise AssertionError("A revoked mandate reopened during update")
    assert json.dumps(service._view(data["view"]), sort_keys=True, default=str) == params.get_str(key + ".view")
    print("MANDATES_PRESERVED: revoked access closed, scoped projection and all previous native evidence unchanged")
else:
    assert not any(
        name.startswith("training_management")
        for name in env["ir.module.module"].search([("state", "=", "installed")]).mapped("name")
    )
    retained = json.loads(params.get_str("autonomous.sales.retained"))
    source = env["training.elearning.sale.allocation"].browse(retained["seat"])
    manager = source.line_id.learning_authorized_by
    representative = new_test_user(env, login="fictional_upgrade_representative", groups="base.group_portal")
    eligible = new_test_user(env, login="fictional_upgrade_delegated_learner", groups="base.group_portal")
    order = env["sale.order"].with_user(manager).create({"partner_id": source.line_id.order_id.partner_id.id})
    line = (
        env["sale.order.line"]
        .with_user(manager)
        .create({"order_id": order.id, "product_id": source.line_id.product_id.id, "product_uom_qty": 1})
    )
    order.action_confirm()
    line.action_learning_authorize("Fictional delegated purchase agreement")
    mandate = (
        env["training.elearning.sale.mandate"]
        .with_user(manager)
        .create(
            {
                "line_id": line.id,
                "user_id": representative.id,
                "can_assign": True,
                "valid_until": fields.Datetime.now() + timedelta(days=500),
                "reason": "Fictional explicit purchase delegation",
                "beneficiary_ids": [Command.set(eligible.partner_id.ids)],
                "revocation_reason": "Fictional concurrent withdrawal",
            }
        )
    )
    mandate.action_grant()
    mandate_id, rep_id, manager_id, partner_id = mandate.id, representative.id, manager.id, eligible.partner_id.id
    context = {"allowed_company_ids": line.company_id.ids}
    env.cr.commit()
    with env.registry.cursor() as assignment, env.registry.cursor() as revocation:
        service = api.Environment(assignment, rep_id, context)["training.elearning.company.service"]
        service._assign(mandate_id, partner_id)
        try:
            api.Environment(revocation, manager_id, context)["training.elearning.sale.mandate"].browse(
                mandate_id
            ).action_revoke()
        except LockError:
            pass
        else:
            raise AssertionError("Mandate revocation ignored the held assignment lock")
        assignment.commit()
        revocation.rollback()
    with env.registry.cursor() as withdrawal:
        api.Environment(withdrawal, manager_id, context)["training.elearning.sale.mandate"].browse(
            mandate_id
        ).action_revoke()
        withdrawal.commit()
    with env.registry.cursor() as replay:
        try:
            api.Environment(replay, rep_id, context)["training.elearning.company.service"]._assign(
                mandate_id, partner_id
            )
        except AccessError:
            pass
        else:
            raise AssertionError("Revoked delegated action was replayed")
    env.cr.rollback()
    env.invalidate_all()
    view = (
        env["training.elearning.sale.mandate"]
        .with_user(manager)
        .create(
            {
                "line_id": line.id,
                "user_id": rep_id,
                "can_assign": False,
                "valid_until": fields.Datetime.now() + timedelta(days=500),
                "reason": "Fictional explicit view-only mandate",
            }
        )
    )
    view.action_grant()
    seat = env["training.elearning.sale.allocation"].search([("line_id", "=", line.id)])
    assert len(seat) == 1 and seat.assigned_by.id == rep_id and seat.assigned_mandate_id.id == mandate_id
    service = env["training.elearning.company.service"].with_user(representative)
    assert [d["id"] for d in service._list()] == [view.id]
    params.set_str(key, json.dumps({"user": rep_id, "revoked": mandate_id, "view": view.id}))
    params.set_str(key + ".view", json.dumps(service._view(view.id), sort_keys=True, default=str))
    evidence = snapshot()
    params.set_str(key + ".snapshot", json.dumps(evidence, sort_keys=True, default=str))
    # Authorized fixture actions add a sale and membership. They become the exact
    # baseline for the later independent check after adding the TM applications.
    params.set_str("autonomous.sales.retained.snapshot", json.dumps(evidence, sort_keys=True, default=str))
    env.cr.commit()
    print("MANDATES_PREPARED: real delegated seat; revocation serialized; no replay or cross-purchase access")
