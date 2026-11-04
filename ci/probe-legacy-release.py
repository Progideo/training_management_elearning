# ruff: noqa: F821 -- native Odoo shell supplies env.
"""Strict original-column preservation across the supported legacy release upgrade."""

import hashlib
import json
from pathlib import Path
from psycopg2 import sql

assert env.cr.dbname in ("tm_suite_test", "tm_suite_restored", "tm_suite_rollback")
params = env["ir.config_parameter"]
key = "qualification.legacy.release.snapshot"
saved = params.get_str(key)
env.flush_all()


def table_rows(table, columns):
    env.cr.execute(sql.SQL("SELECT to_jsonb(t) FROM {} t").format(sql.Identifier(table)))
    rows = [{column: row[0][column] for column in columns} for row in env.cr.fetchall()]
    if table == "ir_attachment":
        rows = [row for row in rows if (row.get("res_model") or "").startswith("training.")]
    return hashlib.sha256(
        json.dumps(sorted(rows, key=lambda row: json.dumps(row, sort_keys=True)), sort_keys=True, default=str).encode()
    ).hexdigest()


if not saved:
    env.cr.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND (tablename LIKE 'training_%%' OR tablename LIKE 'survey_%%' OR tablename IN ('sale_order','sale_order_line','ir_attachment')) ORDER BY tablename"
    )
    data = {"tables": {}}
    for (table,) in env.cr.fetchall():
        env.cr.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
            [table],
        )
        columns = [row[0] for row in env.cr.fetchall()]
        data["tables"][table] = {"columns": columns, "sha256": table_rows(table, columns)}
    params.set_str(key, json.dumps(data))
    env.cr.commit()
    print("J21_LEGACY_ORIGINAL_COLUMNS_AND_BUSINESS_ATTACHMENTS_CAPTURED", len(data["tables"]))
else:
    data = json.loads(saved)
    for table, expected in data["tables"].items():
        assert table_rows(table, expected["columns"]) == expected["sha256"], (
            "Original legacy business evidence changed: " + table
        )
    fixture = json.loads(params.get_str("j15.relocation.fixture"))
    attempt = env["training.elearning.attempt"].with_user(fixture["learner"]).browse(fixture["attempt"])
    assert attempt._snapshot()["state"] == {"location": "retained-step"}
    modern = env["ir.module.module"].search_count(
        [("name", "=", "training_management_interactive"), ("state", "=", "installed")]
    )
    if modern:
        assert env.ref("training_catalog.menu_training_catalogue").id == fixture["menu"]
        assert not env["ir.module.module"].search_count([("state", "in", ("to install", "to upgrade", "to remove"))])
        retired = env["ir.module.module"].search([("name", "=", "training_management_website")])
        assert retired.state == "uninstallable" and not retired.auto_install
    else:
        assert env.ref("training_management_website.menu_training_catalogue").id == fixture["menu"]
    print("J21_LEGACY_ORIGINAL_COLUMNS_AND_RUNTIME_PRESERVED", len(data["tables"]))

root = Path("/var/lib/odoo/filestore") / env.cr.dbname
env.cr.execute("SELECT store_fname,checksum FROM ir_attachment WHERE store_fname IS NOT NULL")
references = env.cr.fetchall()
for name, checksum in references:
    path = (root / name).resolve()
    assert root.resolve() in path.parents and path.is_file(), "A restored attachment file is missing"
    assert not checksum or hashlib.sha1(path.read_bytes()).hexdigest() == checksum, (
        "A restored attachment checksum changed"
    )
print("J21_NATIVE_ATTACHMENT_REFERENCES_AND_HASHES_VALID", len(references))
