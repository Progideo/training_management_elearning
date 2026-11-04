"""Upgrade real fictional J6 business evidence using current addons, without imports."""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TM = Path(os.environ["TM_ADDONS_DIR"]).resolve().parent
PREVIOUS = Path(os.environ["PREVIOUS_EL_ADDONS_DIR"]).resolve()
assert PREVIOUS != ROOT / "addons" and (PREVIOUS / "training_elearning/__manifest__.py").is_file()
sys.path.insert(0, str(TM / "tests/ci"))
from run_suite import Database, checked, assert_tests_ran  # noqa: E402

folder = ROOT / "ci-results/generations"
folder.mkdir(parents=True, exist_ok=True)
(folder / "success.json").unlink(missing_ok=True)
with Database("generations", folder) as db:

    def command(source, *args):
        cmd = db.odoo(
            *args, "--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons,/mnt/elearning-addons"
        )
        index = cmd.index("-e")
        cmd[index:index] = ["-v", f"{source}:/mnt/elearning-addons:ro"]
        return cmd

    checked(
        command(
            PREVIOUS, "-i", "training_elearning_survey,training_elearning_sale", "--without-demo", "--stop-after-init"
        ),
        folder / "previous-install.log",
    )
    probe = ROOT / "ci/probe-generations.py"
    with probe.open() as data:
        checked(command(PREVIOUS, "shell", "--no-http"), folder / "previous-evidence.log", stdin=data)
    text = checked(
        command(
            ROOT / "addons",
            "-u",
            "training_elearning,training_elearning_survey,training_elearning_sale",
            "--stop-after-init",
            "--test-enable",
            "--test-tags=/training_elearning,/training_elearning_survey,/training_elearning_sale,-/web",
        ),
        folder / "current-update.log",
        allow_tracebacks=True,
    )
    assert_tests_ran(text, ["training_elearning", "training_elearning_survey", "training_elearning_sale"])
    with probe.open() as data:
        checked(command(ROOT / "addons", "shell", "--no-http"), folder / "current-preserved.log", stdin=data)
(folder / "success.json").write_text('{"generations": "success"}\n')
