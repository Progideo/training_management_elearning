# ruff: noqa: F821  # Odoo shell supplies env
"""Keep a real partially completed native curriculum across an addon update."""

import json
from odoo import Command, api
from odoo.exceptions import LockError
from odoo.tests import new_test_user

assert env.cr.dbname == "tm_suite_test"
params = env["ir.config_parameter"]
key = "autonomous.paths.retained"
saved = params.get_str(key)
if not saved:
    manager = new_test_user(
        env,
        login="fictional_retained_path_manager",
        groups="training_elearning.group_elearning_manager",
    )
    learner = new_test_user(env, login="fictional_retained_path_learner", groups="base.group_portal")
    catalog = env["training.course"].create({"name": "Fictional retained path catalogue"})
    courses = env["slide.channel"]
    slides = env["slide.slide"]
    for index in range(3):
        course = (
            env["slide.channel"]
            .with_user(manager)
            .create(
                {
                    "name": f"Fictional retained path edition {index}",
                    "training_course_id": catalog.id,
                    "prerequisite_channel_ids": [Command.set(courses[-1:].ids)],
                }
            )
        )
        slide = (
            env["slide.slide"]
            .with_user(manager)
            .create(
                {
                    "name": f"Fictional retained path article {index}",
                    "channel_id": course.id,
                    "slide_category": "article",
                    "html_content": "<p>PRIVATE RETAINED PATH ARTICLE</p>",
                    "is_published": True,
                }
            )
        )
        course.action_learning_publish()
        courses |= course
        slides |= slide
    path = (
        env["training.elearning.path"]
        .with_user(manager)
        .create(
            {
                "name": "Fictional retained curriculum",
                "line_ids": [Command.create({"course_id": c.id}) for c in courses],
            }
        )
    )
    path.action_publish()
    activation = (
        env["training.elearning.path.activation"]
        .with_user(manager)
        ._activate(
            path,
            learner.partner_id,
            path._plan(),
            6,
            12,
            "Fictional retained authorization",
        )
    )
    registration = activation.registration_id
    env["training.elearning.service"].with_user(learner)._declare(registration._member(courses[0].id).id, slides[0].id)
    assert len(activation.item_ids.filtered("activated_at")) == 2
    env.cr.commit()
    # Real independent transactions contend for the same exact native course.
    # The second cannot create a parallel membership or extend the grant twice.
    item_id = activation.item_ids.filtered(lambda item: item.course_id == courses[1]).id
    context = {"allowed_company_ids": path.company_id.ids}
    with env.registry.cursor() as first, env.registry.cursor() as second:
        one = api.Environment(first, manager.id, context)["training.elearning.path.item"].browse(item_id)
        two = api.Environment(second, manager.id, context)["training.elearning.path.item"].browse(item_id)
        one.course_id.lock_for_update()
        try:
            two._start()
        except LockError:
            pass
        else:
            raise AssertionError("Concurrent start ignored the held native course lock")
        second.rollback()
        first.rollback()

    def snapshot():
        return {
            "activation": activation.read(["activated_at", "starts_until", "plan", "access_months"])[0],
            "composition": registration.composition,
            "items": activation.item_ids.read(
                [
                    "course_id",
                    "membership_id",
                    "activated_at",
                    "access_started_at",
                    "access_ends_at",
                    "plan",
                ]
            ),
            "progress": registration._summary(),
        }

    saved = {"activation": activation.id, "snapshot": snapshot()}
    params.set_str(key, json.dumps(saved, default=str, sort_keys=True))
    env.cr.commit()
else:
    saved = json.loads(saved)
    activation = env["training.elearning.path.activation"].browse(saved["activation"])
    registration = activation.registration_id
    current = {
        "activation": activation.read(["activated_at", "starts_until", "plan", "access_months"])[0],
        "composition": registration.composition,
        "items": activation.item_ids.read(
            [
                "course_id",
                "membership_id",
                "activated_at",
                "access_started_at",
                "access_ends_at",
                "plan",
            ]
        ),
        "progress": registration._summary(),
    }
    assert json.loads(json.dumps(current, default=str, sort_keys=True)) == saved["snapshot"]
    activation.item_ids._start_ready()
    assert len(activation.item_ids.filtered("activated_at")) == 2
print("Native curriculum composition, periods, memberships and acquired progress preserved")
