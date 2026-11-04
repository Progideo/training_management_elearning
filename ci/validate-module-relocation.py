"""Relocate the preceding adapter's metadata; preserve real native fictional evidence."""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TM = Path(os.environ["TM_ADDONS_DIR"]).resolve().parent
PREVIOUS_TM = Path(os.environ["PREVIOUS_TM_ADDONS_DIR"]).resolve()
PREVIOUS_EL = Path(os.environ["PREVIOUS_ADAPTER_ADDONS_DIR"]).resolve()
sys.path.insert(0, str(TM / "tests/ci"))
from run_suite import Database, checked, assert_tests_ran  # noqa: E402

folder = ROOT / "ci-results/module-relocation"
folder.mkdir(parents=True, exist_ok=True)
(folder / "success.json").unlink(missing_ok=True)
with Database("module_relocation", folder) as db:

    def command(*args, previous=False):
        cmd = db.odoo(
            *args, "--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons,/mnt/elearning-addons"
        )
        if previous:
            cmd = [item.replace(str(TM / "addons"), str(PREVIOUS_TM)) for item in cmd]
        index = cmd.index("-e")
        cmd[index:index] = ["-v", f"{PREVIOUS_EL if previous else ROOT / 'addons'}:/mnt/elearning-addons:ro"]
        return cmd

    checked(
        command(
            "-i",
            "training_management_elearning,training_management_website",
            "--without-demo",
            "--stop-after-init",
            previous=True,
        ),
        folder / "previous-install.log",
    )
    for name in ("prepare", "snapshot"):
        with (ROOT / f"ci/probe-module-relocation-{name}.py").open() as data:
            checked(command("shell", "--no-http", previous=True), folder / f"previous-{name}.log", stdin=data)
    script = (TM / "tools/relocate_modules.py").read_text() + "\nenv.cr.commit()\n"
    script_file = folder / "relocate-shell.py"
    script_file.write_text(script)
    with script_file.open() as data:
        checked(command("shell", "--no-http", previous=True), folder / "relocate.log", stdin=data)
    for phase in ("update", "repeat-update"):
        text = checked(
            command(
                "-u",
                "training_catalog,training_management_interactive",
                "--test-enable",
                "--test-tags=/training_management_interactive,-/web",
                "--stop-after-init",
            ),
            folder / f"{phase}.log",
            allow_tracebacks=True,
        )
        assert_tests_ran(text, ["training_management_interactive"])
        with (ROOT / "ci/probe-module-relocation-snapshot.py").open() as data:
            text = checked(command("shell", "--no-http"), folder / f"{phase}-preserved.log", stdin=data)
        assert "J15_BUSINESS_ROWS_ATTACHMENTS_STATE_MENU_IDENTICAL" in text
        with script_file.open() as data:
            checked(command("shell", "--no-http"), folder / f"{phase}-idempotent.log", stdin=data)
(folder / "success.json").write_text('{"module_relocation":"success"}\n')
