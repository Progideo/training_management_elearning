"""Install and update the autonomous composition without the TM business apps."""

import ast
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
compatibility = json.loads((ROOT / "compatibility.json").read_text())
for addon, version in compatibility["autonomous_addons"].items():
    manifest = ast.literal_eval((ROOT / "addons" / addon / "__manifest__.py").read_text())
    assert manifest["version"] == version
    assert not any(dependency.startswith("training_management") for dependency in manifest["depends"])
TM = Path(os.environ["TM_ADDONS_DIR"]).resolve().parent
sys.path.insert(0, str(TM / "tests/ci"))
from run_suite import Database, checked, assert_tests_ran  # noqa: E402

folder = ROOT / "ci-results/autonomous"
folder.mkdir(parents=True, exist_ok=True)
(folder / "success.json").unlink(missing_ok=True)

with Database("autonomous", folder) as db:

    def command(*args):
        cmd = db.odoo(
            *args, "--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons,/mnt/elearning-addons"
        )
        index = cmd.index("-e")
        cmd[index:index] = ["-v", f"{ROOT / 'addons'}:/mnt/elearning-addons:ro"]
        return cmd

    addons = ["training_elearning_survey", "training_mock_exam"]
    text = checked(
        command(
            "-i",
            "training_elearning_survey",
            "--without-demo",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_elearning_survey,/training_mock_exam,-/web",
        ),
        folder / "install.log",
        allow_tracebacks=True,
    )
    assert_tests_ran(text, addons)
    probe = ROOT / "ci/probe-autonomous.py"
    with probe.open() as data:
        checked(command("shell", "--no-http"), folder / "prepare.log", stdin=data)
    text = checked(
        command(
            "-u",
            "training_elearning,training_elearning_survey,training_mock_exam",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_elearning_survey,/training_mock_exam,-/web",
        ),
        folder / "update.log",
        allow_tracebacks=True,
    )
    assert_tests_ran(text, addons)
    with probe.open() as data:
        checked(command("shell", "--no-http"), folder / "preserved.log", stdin=data)
    text = checked(
        command(
            "-i",
            "training_elearning_sale",
            "--without-demo",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_elearning_sale,-/web",
        ),
        folder / "sales-install.log",
        allow_tracebacks=True,
    )
    assert_tests_ran(text, ["training_elearning_sale"])
    with probe.open() as data:
        checked(command("shell", "--no-http"), folder / "sales-existing-preserved.log", stdin=data)
    sales_probe = ROOT / "ci/probe-sales.py"
    with sales_probe.open() as data:
        checked(command("shell", "--no-http"), folder / "sales-prepare.log", stdin=data)
    text = checked(
        command(
            "-u",
            "training_elearning_sale,training_elearning_survey",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_elearning_sale,/training_elearning_survey,-/web",
        ),
        folder / "sales-update.log",
        allow_tracebacks=True,
    )
    assert_tests_ran(text, ["training_elearning_sale", "training_elearning_survey"])
    with sales_probe.open() as data:
        checked(command("shell", "--no-http"), folder / "sales-preserved.log", stdin=data)
    # A separate final phase intentionally adds TM and checks cross-app context
    # isolation. Independence was asserted before adding any TM business model.
    text = checked(
        command(
            "-i",
            "training_management_survey",
            "--without-demo",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_management_survey:TestExamRequirements.test_coexisting_autonomous_offer_keeps_evidence_and_reader_scope_separate",
        ),
        folder / "coexistence.log",
        allow_tracebacks=True,
    )
    assert_tests_ran(text, ["training_management_survey"])
(folder / "success.json").write_text('{"autonomous": "success"}\n')
