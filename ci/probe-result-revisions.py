# ruff: noqa: F821 -- native Odoo shell provides env.
"""Real three-transaction grading contention and unchanged native evidence after update."""

import json
from datetime import timedelta
from uuid import uuid4
from odoo import api, Command, fields
from odoo.exceptions import LockError
from odoo.tests import new_test_user
from psycopg2.errors import SerializationFailure

assert env.cr.dbname == "tm_suite_test"
key = "autonomous.results.revision.retained"
params = env["ir.config_parameter"]
saved = params.get_str(key)


def snapshot(attempt):
    env.flush_all()
    member = attempt.learning_membership_id
    leaf = (
        env["slide.slide.partner"]
        .sudo()
        .search([("slide_id", "=", attempt.learning_slide_id.id), ("partner_id", "=", member.partner_id.id)])
    )
    return {
        "attempt": attempt.read(
            [
                "id",
                "survey_id",
                "partner_id",
                "mock_context_key",
                "mock_revision_serial",
                "start_datetime",
                "deadline",
                "end_datetime",
                "state",
                "scoring_total",
                "scoring_percentage",
            ]
        ),
        "answers": attempt.user_input_line_ids.sorted("id").read(
            [
                "id",
                "question_id",
                "suggested_answer_id",
                "answer_score",
                "answer_is_correct",
                "create_date",
                "write_date",
            ]
        ),
        "revisions": attempt.training_adjustment_ids.sorted("id").read(
            [
                "id",
                "attempt_id",
                "company_id",
                "reason",
                "revised_at",
                "points_by_question",
                "author_id",
                "previous_id",
                "request_key",
                "create_date",
                "write_date",
            ]
        ),
        "member": member.read(["id", "learning_plan", "completion", "member_status"]),
        "leaf": leaf.read(["id", "slide_id", "partner_id", "completed", "learning_completed_at"]),
    }


if not saved:
    manager = new_test_user(
        env,
        login="fictional_retained_result_coordinator",
        groups="training_elearning_survey.group_learning_exam_reader",
    )
    learner = new_test_user(env, login="fictional_retained_result_learner", groups="base.group_portal")
    catalog = env["training.course"].create({"name": "Fictional retained result catalogue"})
    exam = (
        env["survey.survey"]
        .with_user(manager)
        .create(
            {
                "title": "Fictional retained result exam",
                "training_course_id": catalog.id,
                "time_limit": 15,
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
                "title": "Fictional retained question",
                "question_type": "simple_choice",
                "answer_score": 2,
                "training_theme": "Fictional retained theme",
                "training_explanation": "Fictional private correction",
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
        .create({"name": "Fictional retained result edition", "training_course_id": catalog.id})
    )
    slide = (
        env["slide.slide"]
        .with_user(manager)
        .create(
            {"channel_id": course.id, "survey_id": exam.id, "learning_exam_obligation": "pass", "is_published": True}
        )
    )
    course.action_learning_publish()
    member = (
        env["slide.channel.partner"]
        .with_user(manager)
        .create({"channel_id": course.id, "partner_id": learner.partner_id.id})
    )
    member.action_learning_activate(
        fields.Datetime.now() + timedelta(days=2), learner.id, "Fictional retained result grant"
    )
    service = env["training.elearning.exam.service"].with_user(learner)
    attempt = service._start(member.id, slide.id)
    service._save(
        attempt.id, question.id, question.suggested_answer_ids.filtered(lambda choice: not choice.is_correct).ids, False
    )
    service._submit(attempt.id)
    attempt_id, manager_id = attempt.id, manager.id
    points = {str(question.id): 2}
    request_key = str(uuid4())
    env.cr.commit()  # Fictional fixture must be visible to independent cursors.
    with env.registry.cursor() as winning_cr, env.registry.cursor() as old_cr:
        winning = api.Environment(winning_cr, manager_id, {})
        old = api.Environment(old_cr, manager_id, {})
        old_attempt = old["survey.user_input"].browse(attempt_id)
        old_attempt.read(["state", "mock_revision_serial"])  # Establish the old RR snapshot.
        winner = winning["training.exam.revision"]._record(
            winning["survey.user_input"].browse(attempt_id),
            points,
            "Fictional contended result review",
            request_key=request_key,
            expected_previous=0,
        )
        winner_id = winner.id
        try:
            old["training.exam.revision"]._record(
                old_attempt, points, "Fictional contended result review", request_key=request_key, expected_previous=0
            )
        except LockError:
            print("J17_HELD_RESULT_CONTEXT_REFUSED")
        else:
            raise AssertionError("A held result context was not protected")
        winning_cr.commit()
        try:
            old["training.exam.revision"]._record(
                old_attempt, points, "Fictional contended result review", request_key=request_key, expected_previous=0
            )
        except (LockError, SerializationFailure):
            print("J17_OLD_RESULT_SNAPSHOT_REFUSED")
        else:
            raise AssertionError("A stale result snapshot was not rejected")
        old_cr.rollback()
    with env.registry.cursor() as retry_cr:
        retry = api.Environment(retry_cr, manager_id, {})
        same = retry["training.exam.revision"]._record(
            retry["survey.user_input"].browse(attempt_id),
            points,
            "Fictional contended result review",
            request_key=request_key,
            expected_previous=0,
        )
        assert same.id == winner_id
        assert retry["training.exam.revision"].search_count([("attempt_id", "=", attempt_id)]) == 1
        retry_cr.commit()
    env.cr.rollback()
    env.invalidate_all()
    attempt = env["survey.user_input"].browse(attempt_id)
    assert attempt.scoring_percentage == 0 and attempt.learning_membership_id.completion == 100
    params.set_str(key, json.dumps({"attempt": attempt_id, "snapshot": snapshot(attempt)}, default=str))
    env.cr.commit()
    print("J17_RESULT_RETRY_SAME_EVENT_AND_NATIVE_ANSWERS_UNCHANGED")
else:
    data = json.loads(saved)
    assert (
        json.loads(json.dumps(snapshot(env["survey.user_input"].browse(data["attempt"])), default=str))
        == data["snapshot"]
    )
    print("J17_RESULT_REVISIONS_NATIVE_ANSWERS_CLOCK_AND_FIRST_ACQUISITION_PRESERVED")
