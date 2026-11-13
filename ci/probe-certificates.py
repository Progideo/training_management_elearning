# ruff: noqa: F821  # Odoo shell supplies env
"""Keep native consent, replacement history and real immutable PDF bytes through upgrade."""

import hashlib
import json
from datetime import timedelta
from odoo import api, fields
from odoo.exceptions import LockError
from psycopg2.errors import SerializationFailure
from odoo.tests import new_test_user

assert env.cr.dbname == "tm_suite_test"
params = env["ir.config_parameter"]
key = "autonomous.certificates.retained"
saved = params.get_str(key)
if not saved:
    manager = new_test_user(
        env,
        login="fictional_retained_certificate_coordinator",
        groups="training_elearning.group_elearning_pedagogy_manager",
    )
    learner = new_test_user(env, login="fictional_retained_certificate_holder", groups="base.group_portal")
    catalog = env["training.course"].create({"name": "Fictional retained certificate catalogue"})
    course = (
        env["slide.channel"]
        .with_user(manager)
        .create({"name": "Fictional retained certificate edition", "training_course_id": catalog.id})
    )
    slide = (
        env["slide.slide"]
        .with_user(manager)
        .create(
            {
                "channel_id": course.id,
                "name": "Fictional retained certificate article",
                "slide_category": "article",
                "html_content": "<p>PRIVATE RETAINED CERTIFICATE ARTICLE</p>",
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
        fields.Datetime.now() + timedelta(days=2), learner.id, "Fictional retained certificate grant"
    )
    env["training.elearning.service"].with_user(learner)._declare(member.id, slide.id)
    service = env["training.elearning.certificate.service"].with_user(learner)
    accepted = service._prepare(membership_id=member.id)
    accepted._decide(True)
    first = accepted.with_user(manager)._issue()
    old = first.pdf.content
    learner.partner_id.name = "Fictional retained corrected holder"
    fresh = service._prepare(membership_id=member.id)
    fresh._decide(True)
    second = fresh.with_user(manager)._issue(replacement_reason="Fictional retained corrected identity")
    assert first.state == "replaced" and second.state == "valid"
    assert first.pdf.content == old
    service._own_document(first.id)._disable_public("Fictional retained holder privacy request", owner=True)
    contender = service._prepare(membership_id=member.id)
    contender._decide(True)
    stale = service._prepare(membership_id=member.id)
    stale._decide(True)
    manager_id, contender_id, stale_id = manager.id, contender.id, stale.id
    context = {"allowed_company_ids": course.learning_company_id.ids}
    env.cr.commit()
    with env.registry.cursor() as winner, env.registry.cursor() as old_snapshot, env.registry.cursor() as held:
        stale_request = api.Environment(old_snapshot, manager_id, context)[
            "training.elearning.certificate.consent"
        ].browse(stale_id)
        assert stale_request.state == "accepted"  # establish repeatable-read snapshot
        issued = (
            api.Environment(winner, manager_id, context)["training.elearning.certificate.consent"]
            .browse(contender_id)
            ._issue(replacement_reason="Fictional concurrent replacement")
        )
        third_id = issued.id
        try:
            api.Environment(held, manager_id, context)["training.elearning.certificate.consent"].browse(
                stale_id
            )._issue(replacement_reason="Fictional held-lock replacement")
        except LockError:
            pass
        else:
            raise AssertionError("Concurrent certificate issue ignored the source lock")
        held.rollback()
        winner.commit()
        try:
            stale_request._issue(replacement_reason="Fictional stale-snapshot replacement")
        except (LockError, SerializationFailure):
            pass  # Native request retrying starts a fresh snapshot for this conflict.
        else:
            raise AssertionError("Stale consent ignored the committed source revision")
        old_snapshot.rollback()
    with env.registry.cursor() as retry:
        repeated = (
            api.Environment(retry, manager_id, context)["training.elearning.certificate.consent"]
            .browse(contender_id)
            ._issue()
        )
        assert repeated.id == third_id
        retry.rollback()
    env.cr.rollback()
    env.invalidate_all()
    third = env["training.elearning.certificate"].browse(third_id)
    documents = first | second | third
    env.flush_all()
    saved = {
        "documents": documents.ids,
        "pdfs": {str(doc.id): hashlib.sha256(doc.pdf.content).hexdigest() for doc in documents},
    }
    for table, ids in (
        ("training_elearning_certificate", documents.ids),
        ("training_elearning_certificate_consent", (accepted | fresh | contender | stale).ids),
    ):
        env.cr.execute(f"SELECT to_jsonb(t) - 'pdf' FROM {table} t WHERE id = ANY(%s) ORDER BY id", [ids])
        saved[table] = {"ids": ids, "rows": [row[0] for row in env.cr.fetchall()]}
    params.set_str(key, json.dumps(saved, sort_keys=True))
    env.cr.commit()
else:
    saved = json.loads(saved)
    for table in ("training_elearning_certificate", "training_elearning_certificate_consent"):
        data = saved[table]
        env.cr.execute(f"SELECT to_jsonb(t) - 'pdf' FROM {table} t WHERE id = ANY(%s) ORDER BY id", [data["ids"]])
        assert [row[0] for row in env.cr.fetchall()] == data["rows"]
    documents = env["training.elearning.certificate"].browse(saved["documents"])
    for document in documents:
        assert hashlib.sha256(document.pdf.content).hexdigest() == saved["pdfs"][str(document.id)]
    assert documents[0].state == "replaced" and not documents[0].public_enabled
    assert documents[-1].state == "valid" and documents[-1].public_enabled
    assert all(document.state == "replaced" for document in documents[:-1])
print("Explicit certificate consents, replacement status, public settings and immutable native PDF bytes preserved")
