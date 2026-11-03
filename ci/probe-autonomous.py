# ruff: noqa: F821  # Odoo shell supplies env
"""Real native evidence retained across update, with no Training Management installed."""

import json
from datetime import timedelta
from odoo import fields, Command
from odoo.tests import new_test_user

assert env.cr.dbname == "tm_suite_test"
installed = env["ir.module.module"].search([("state", "=", "installed")]).mapped("name")
assert "training_elearning_survey" in installed
assert not any(name.startswith("training_management") for name in installed), installed
params = env["ir.config_parameter"]
key = "autonomous.retained.native.evidence"
saved = params.get_str(key)
if not saved:
    manager = new_test_user(
        env, login="fictional_upgrade_coordinator", groups="training_elearning_survey.group_learning_exam_reader"
    )
    learner = new_test_user(env, login="fictional_upgrade_learner", groups="base.group_portal")
    catalog = env["training.course"].create({"name": "Fictional retained autonomous catalogue"})
    exam = (
        env["survey.survey"]
        .with_user(manager)
        .create(
            {
                "title": "Fictional retained version",
                "training_course_id": catalog.id,
                "time_limit": 10,
                "scoring_success_min": 75,
            }
        )
    )
    question = (
        env["survey.question"]
        .with_user(manager)
        .create(
            {
                "survey_id": exam.id,
                "title": "Fictional question",
                "question_type": "simple_choice",
                "answer_score": 2,
                "suggested_answer_ids": [
                    Command.create({"value": "Expected", "is_correct": True}),
                    Command.create({"value": "Other"}),
                ],
            }
        )
    )
    exam.action_mock_publish()
    course = (
        env["slide.channel"]
        .with_user(manager)
        .create({"name": "Fictional retained edition", "training_course_id": catalog.id})
    )
    slide = (
        env["slide.slide"]
        .with_user(manager)
        .create(
            {"channel_id": course.id, "survey_id": exam.id, "is_published": True, "learning_exam_obligation": "pass"}
        )
    )
    course.action_learning_publish()
    member = (
        env["slide.channel.partner"]
        .with_user(manager)
        .create({"channel_id": course.id, "partner_id": learner.partner_id.id})
    )
    member.action_learning_activate(
        fields.Datetime.now() + timedelta(days=2), learner.id, "Fictional controlled access"
    )
    service = env["training.elearning.exam.service"].with_user(learner)
    answer = service._start(member.id, slide.id)
    service._save(answer.id, question.id, question.suggested_answer_ids.filtered("is_correct").ids, False)
    service._submit(answer.id)
    assert member.completion == 100
    params.set_str(key, json.dumps({"member": member.id, "answer": answer.id}))


def snapshot():
    env.flush_all()
    result = {}
    for table in (
        "slide_channel_partner",
        "survey_user_input",
        "survey_user_input_line",
        "training_elearning_exam_requirement",
    ):
        env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id")
        result[table] = [row[0] for row in env.cr.fetchall()]
    return json.dumps(result, sort_keys=True, default=str)


if not saved:
    params.set_str(key + ".snapshot", snapshot())
    env.cr.commit()
    print("AUTONOMOUS_PREPARED: native completion, frozen requirement, Survey answers and timing")
else:
    assert snapshot() == params.get_str(key + ".snapshot"), "Autonomous native evidence changed during update"
    print("AUTONOMOUS_PRESERVED: exact native evidence; no TM business addon installed")
