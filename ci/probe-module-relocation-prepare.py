# ruff: noqa: F821
from uuid import uuid4
import json
from odoo.tests import new_test_user
from odoo.addons.training_management_elearning.tests.test_content_security import package

assert env.cr.dbname == "tm_suite_test"
coordinator = new_test_user(
    env, login="fictional_j15_coordinator", groups="training_management.group_training_coordinator"
)
learner = new_test_user(env, login="fictional_j15_learner", groups="base.group_portal")
customer = env["res.partner"].create({"name": "Fictional J15 buyer"})
course = env["training.course"].create({"name": "Fictional retained J15 course"})
course.category_id = env["training.category"].create({"name": "Fictional J15 category"}).id
program = env["training.program.version"].create(
    {
        "course_id": course.id,
        "version": "J15-1",
        "title": "Fictional J15 programme",
        "objectives": "Practice",
        "target_audience": "Beginners",
        "prerequisites": "Reviewed manually",
        "content": "Private contents",
        "duration_hours": 7,
        "delivery_mode": "remote",
        "language_id": env.ref("base.lang_en").id,
        "teaching_methods": "Exercises",
        "evaluation_criteria": "Review",
        "access_conditions": "Authorization",
        "accessibility_contact_id": customer.id,
        "accessibility_information": "Contact coordination",
    }
)
program.action_validate()
resource = (
    env["training.elearning.resource"]
    .with_user(coordinator)
    .create({"name": "Fictional retained J15 package", "format": "scorm12"})
)
version = (
    env["training.elearning.version"]
    .with_user(coordinator)
    ._import(resource, "J15-1", package(), "Fictional licence", "Fictional source")
)
version.action_publish()
assignment = (
    env["training.elearning.assignment"]
    .with_user(coordinator)
    .create(
        {
            "name": "Fictional formative J15",
            "program_id": program.id,
            "version_id": version.id,
            "objective": "Practice",
            "rule": "score",
            "threshold": 70,
        }
    )
)
assignment.action_validate()
delivery = (
    env["training.delivery"]
    .with_user(coordinator)
    .create(
        {
            "name": "Fictional retained J15 delivery",
            "program_id": program.id,
            "kind": "autonomous",
            "capacity": 10,
            "access_policy": "duration",
            "access_days": 10,
        }
    )
)
usage = assignment._apply(delivery)
enrollment = (
    env["training.enrollment"]
    .with_user(coordinator)
    .create(
        {
            "delivery_id": delivery.id,
            "participant_id": learner.partner_id.id,
            "user_id": learner.id,
            "free_reason": "Fictional invitation",
        }
    )
)
enrollment.action_validate_prerequisites(reason="Fictional manual review")
enrollment.action_confirm()
enrollment.action_authorize(reason="Fictional authorization")
enrollment.action_open_access(reason="Fictional opening")
attempt = env["training.elearning.attempt"].with_user(learner)._start(enrollment.id, usage.id, str(uuid4()))
attempt._save(
    "fictional-j15-pass",
    1,
    {"state": {"location": "retained-step"}, "result": {"score": 80, "maximum": 100, "completed": True}},
)
menu = env.ref("training_management_website.menu_training_catalogue")
menu.write({"name": "Fictional customized Formations", "sequence": 37})
env.flush_all()
params = env["ir.config_parameter"]
params.set_str("j15.relocation.fixture", json.dumps({"learner": learner.id, "attempt": attempt.id, "menu": menu.id}))
env.cr.commit()
print("J15_FICTIONAL_RUNTIME_PREPARED")
