# ruff: noqa: F821
import hashlib
import json
from psycopg2 import sql

assert env.cr.dbname == "tm_suite_test"
env.flush_all()
tables = [
    "training_elearning_resource",
    "training_elearning_version",
    "training_elearning_file",
    "training_elearning_assignment",
    "training_elearning_usage",
    "training_elearning_attempt",
    "training_elearning_event",
    "training_learning_progress",
    "training_enrollment",
    "training_program_version",
    "ir_attachment",
]
actual = {}
for table in tables:
    env.cr.execute(
        sql.SQL(
            "SELECT * FROM {} WHERE res_model LIKE 'training.%%' ORDER BY id"
            if table == "ir_attachment"
            else "SELECT * FROM {} ORDER BY id"
        ).format(sql.Identifier(table))
    )
    actual[table] = hashlib.sha256(
        json.dumps(
            env.cr.fetchall(),
            default=lambda value: (
                hashlib.sha256(bytes(value)).hexdigest() if isinstance(value, (bytes, memoryview)) else str(value)
            ),
        ).encode()
    ).hexdigest()
params = env["ir.config_parameter"]
previous = params.get_str("j15.relocation.snapshot")
if previous:
    assert actual == json.loads(previous), (actual, json.loads(previous))
    fixture = json.loads(params.get_str("j15.relocation.fixture"))
    attempt = env["training.elearning.attempt"].with_user(fixture["learner"]).browse(fixture["attempt"])
    assert attempt._snapshot()["state"] == {"location": "retained-step"}
    menu = env.ref("training_catalog.menu_training_catalogue")
    assert menu.id == fixture["menu"] and menu.name == "Fictional customized Formations" and menu.sequence == 37
    assert env.ref("training_management_interactive.group_elearning_author")
    assert not env["ir.model.data"].search_count([("module", "=", "training_management_elearning")])
    retired = env["ir.module.module"].search([("name", "=", "training_management_website")])
    assert retired.state == "uninstallable" and not retired.auto_install
    assert not env["ir.module.module"].search_count(
        [
            ("name", "in", ["training_management_website", "training_management_elearning"]),
            ("state", "in", ["installed", "to install", "to upgrade", "to remove"]),
        ]
    )
    print("J15_BUSINESS_ROWS_ATTACHMENTS_STATE_MENU_IDENTICAL")
else:
    params.set_str("j15.relocation.snapshot", json.dumps(actual))
    env.cr.commit()
    print("J15_BUSINESS_SNAPSHOT_PREPARED")
