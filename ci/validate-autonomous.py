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
            *args,
            "--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons,/mnt/elearning-addons",
        )
        index = cmd.index("-e")
        cmd[index:index] = ["-v", f"{ROOT / 'addons'}:/mnt/elearning-addons:ro"]
        return cmd

    # Prove that declarative lessons do not require Survey, Sales or TM.
    text = checked(
        command(
            "-i",
            "training_elearning",
            "--without-demo",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_elearning,-/web",
        ),
        folder / "lessons-install.log",
        allow_tracebacks=True,
    )
    assert_tests_ran(text, ["training_elearning"])
    with (ROOT / "ci/probe-lessons.py").open() as data:
        checked(command("shell", "--no-http"), folder / "lessons-prepare.log", stdin=data)
    with (ROOT / "ci/probe-practicals.py").open() as data:
        checked(command("shell", "--no-http"), folder / "practicals-prepare.log", stdin=data)
    with (ROOT / "ci/probe-human-practicals.py").open() as data:
        checked(
            command("shell", "--no-http"),
            folder / "human-practicals-prepare.log",
            stdin=data,
        )
    with (ROOT / "ci/probe-paths.py").open() as data:
        checked(command("shell", "--no-http"), folder / "paths-prepare.log", stdin=data)
    with (ROOT / "ci/probe-certificates.py").open() as data:
        checked(command("shell", "--no-http"), folder / "certificates-prepare.log", stdin=data)
    text = checked(
        command(
            "-u",
            "training_elearning",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_elearning,-/web",
        ),
        folder / "lessons-update.log",
        allow_tracebacks=True,
    )
    assert_tests_ran(text, ["training_elearning"])
    with (ROOT / "ci/probe-lessons.py").open() as data:
        checked(command("shell", "--no-http"), folder / "lessons-preserved.log", stdin=data)

    with (ROOT / "ci/probe-practicals.py").open() as data:
        checked(
            command("shell", "--no-http"),
            folder / "practicals-preserved.log",
            stdin=data,
        )
    with (ROOT / "ci/probe-human-practicals.py").open() as data:
        checked(
            command("shell", "--no-http"),
            folder / "human-practicals-preserved.log",
            stdin=data,
        )

    with (ROOT / "ci/probe-paths.py").open() as data:
        checked(command("shell", "--no-http"), folder / "paths-preserved.log", stdin=data)
    with (ROOT / "ci/probe-certificates.py").open() as data:
        checked(command("shell", "--no-http"), folder / "certificates-preserved.log", stdin=data)

    addons = ["training_elearning", "training_elearning_survey", "training_mock_exam"]
    text = checked(
        command(
            "-i",
            "training_elearning_survey",
            "-u",
            "training_elearning",
            "--without-demo",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_elearning,/training_elearning_survey,/training_mock_exam,-/web",
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
            "--test-tags=/training_elearning,/training_elearning_survey,/training_mock_exam,-/web",
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
        checked(
            command("shell", "--no-http"),
            folder / "sales-existing-preserved.log",
            stdin=data,
        )
    with (ROOT / "ci/probe-capacity.py").open() as data:
        checked(
            command("shell", "--no-http"),
            folder / "capacity-concurrency.log",
            stdin=data,
        )
    with (ROOT / "ci/probe-purchase-reports.py").open() as data:
        checked(command("shell", "--no-http"), folder / "purchase-reports-prepare.log", stdin=data)
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
    with (ROOT / "ci/probe-purchase-reports.py").open() as data:
        checked(command("shell", "--no-http"), folder / "purchase-reports-preserved.log", stdin=data)
    mandates_probe = ROOT / "ci/probe-mandates.py"
    with mandates_probe.open() as data:
        checked(command("shell", "--no-http"), folder / "mandates-prepare.log", stdin=data)
    text = checked(
        command(
            "-u",
            "training_elearning_sale",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_elearning_sale,-/web",
        ),
        folder / "mandates-update.log",
        allow_tracebacks=True,
    )
    assert_tests_ran(text, ["training_elearning_sale"])
    with mandates_probe.open() as data:
        checked(command("shell", "--no-http"), folder / "mandates-preserved.log", stdin=data)
    # A separate final phase intentionally adds TM and checks cross-app context
    # isolation. Independence was asserted before adding any TM business model.
    text = checked(
        command(
            "-i",
            "training_management_survey,training_management_sale",
            "-u",
            "training_elearning_sale",
            "--without-demo",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_management_survey:TestExamRequirements.test_coexisting_autonomous_offer_keeps_evidence_and_reader_scope_separate,/training_management_sale,/training_elearning_sale,-/web",
        ),
        folder / "coexistence.log",
        allow_tracebacks=True,
    )
    assert_tests_ran(
        text,
        [
            "training_management_survey",
            "training_management_sale",
            "training_elearning_sale",
        ],
    )
    with (ROOT / "ci/probe-sales-coexistence.py").open() as data:
        checked(
            command("shell", "--no-http"),
            folder / "coexistence-preserved.log",
            stdin=data,
        )
    with mandates_probe.open() as data:
        checked(
            command("shell", "--no-http"),
            folder / "mandates-coexistence-preserved.log",
            stdin=data,
        )
# The sales bridge must not smuggle in the optional Survey integration.
with Database("sales_without_survey", folder / "sales-without-survey") as db:
    cmd = db.odoo(
        "-i",
        "training_elearning_sale",
        "--without-demo",
        "--stop-after-init",
        "--test-enable",
        "--test-tags=/training_elearning_sale:TestNativeCourseSales,/training_elearning_sale:TestPracticalSalePolicy,/training_elearning_sale:TestPathSales,/training_elearning_sale:TestPurchaseReports,-/web",
        "--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons,/mnt/elearning-addons",
    )
    index = cmd.index("-e")
    cmd[index:index] = ["-v", f"{ROOT / 'addons'}:/mnt/elearning-addons:ro"]
    text = checked(cmd, folder / "sales-without-survey/install.log", allow_tracebacks=True)
    assert_tests_ran(text, ["training_elearning_sale"])
    probe = (
        "assert 'survey.survey' not in env; assert 'training.enrollment' not in env; print('SALES_WITHOUT_SURVEY_OK')"
    )
    with (folder / "sales-without-survey/probe.py").open("w") as script:
        script.write(probe + "\n")
    cmd = db.odoo(
        "shell",
        "--no-http",
        "--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons,/mnt/elearning-addons",
    )
    index = cmd.index("-e")
    cmd[index:index] = ["-v", f"{ROOT / 'addons'}:/mnt/elearning-addons:ro"]
    with (folder / "sales-without-survey/probe.py").open() as script:
        checked(cmd, folder / "sales-without-survey/independence.log", stdin=script)
(folder / "success.json").write_text('{"autonomous": "success"}\n')
