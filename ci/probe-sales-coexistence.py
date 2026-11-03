# ruff: noqa: F821  # Odoo shell supplies env
"""Adding TM must retain every previously stored sales and autonomous proof value."""

import json

assert env.cr.dbname == "tm_suite_test"
assert "training.enrollment" in env
retained = json.loads(env["ir.config_parameter"].get_str("autonomous.sales.retained.snapshot"))
for table, expected in retained.items():
    env.cr.execute(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id")
    current = [row[0] for row in env.cr.fetchall()]
    assert len(current) == len(expected), (table, "Unexpected proof creation or deletion")
    for before, after in zip(expected, current):
        # New optional adapter columns are outside the previous schema. Every
        # original value, including audit dates and grant state, stays exact.
        assert {key: after[key] for key in before} == before, (
            table,
            before["id"],
            [key for key in before if before[key] != after[key]],
        )
print("AUTONOMOUS_SALES_COEXISTENCE_PRESERVED: all prior native values and audit dates remain exact after adding TM")
