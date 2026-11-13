"""All-app coexistence, upgrade from the initial supported release and real backup/restore."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TM = Path(os.environ["TM_ADDONS_DIR"]).resolve().parent
PREVIOUS_TM = Path(os.environ["PREVIOUS_RELEASE_TM_ADDONS_DIR"]).resolve()
PREVIOUS_EL = Path(os.environ["PREVIOUS_RELEASE_EL_ADDONS_DIR"]).resolve()
sys.path.insert(0, str(TM / "tests/ci"))
from run_suite import Database, checked, assert_tests_ran  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--phase", choices=("all", "fresh", "legacy"), default="all")
phase = parser.parse_args().phase

compatibility = json.loads((ROOT / "compatibility.json").read_text())
image = compatibility["odoo_image"]
folder = ROOT / "ci-results" / ("final-release" if phase == "all" else "final-release-" + phase)
folder.mkdir(parents=True, exist_ok=True)
(folder / "success.json").unlink(missing_ok=True)
addons = [
    "training_catalog",
    "training_interactive",
    "training_mock_exam",
    "training_management",
    "training_management_sale",
    "training_management_survey",
    "training_management_interactive",
    "training_elearning",
    "training_elearning_sale",
    "training_elearning_survey",
]
regional = "sale_invoice_address_fiscal"


def command(db, *args, previous=False, database="tm_suite_test", phase=None):
    cmd = db.odoo(
        *args, "--addons-path=/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons,/mnt/elearning-addons"
    )
    if previous:
        cmd = [item.replace(str(TM / "addons"), str(PREVIOUS_TM)) for item in cmd]
    cmd[cmd.index("-d") + 1] = database
    index = cmd.index("-e")
    mounts = ["-v", f"{PREVIOUS_EL if previous else ROOT / 'addons'}:/mnt/elearning-addons:ro"]
    if phase:
        mounts += ["-e", phase]
    cmd[index:index] = mounts
    return cmd


def shell(db, name, source, **options):
    path = folder / (name + ".py")
    path.write_text(source)
    with path.open() as data:
        return checked(command(db, "shell", "--no-http", **options), folder / (name + ".log"), stdin=data)


def backup(db, destination):
    dump = destination / "database.dump"
    with dump.open("wb") as output:
        subprocess.run(
            ["docker", "exec", db.name + "_pg", "pg_dump", "-Fc", "-U", "odoo", "-d", "tm_suite_test"],
            stdout=output,
            check=True,
        )
    archive = destination / "filestore.tar.gz"
    source = "import tarfile,sys\nwith tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:\n archive.add('/var/lib/odoo/filestore/tm_suite_test',arcname='filestore')\n"
    with archive.open("wb") as output:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                db.name + "_data:/var/lib/odoo:ro",
                "--entrypoint",
                "python3",
                image,
                "-c",
                source,
            ],
            stdout=output,
            check=True,
        )
    return dump, archive


def restore(db, dump, archive, database):
    subprocess.run(["docker", "exec", db.name + "_pg", "createdb", "-U", "odoo", database], check=True)
    with dump.open("rb") as data:
        subprocess.run(
            ["docker", "exec", "-i", db.name + "_pg", "pg_restore", "--no-owner", "-U", "odoo", "-d", database],
            stdin=data,
            check=True,
        )
    source = (
        "import tarfile,sys,pathlib\nroot=pathlib.Path('/var/lib/odoo/filestore')/"
        + repr(database)
        + "\nroot.mkdir(parents=True)\nwith tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as archive:\n for item in archive:\n  relative=pathlib.PurePosixPath(item.name).relative_to('filestore')\n  item.name=str(relative)\n  archive.extract(item,root,filter='data')\n"
    )
    with archive.open("rb") as data:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                "-v",
                db.name + "_data:/var/lib/odoo",
                "--entrypoint",
                "python3",
                image,
                "-c",
                source,
            ],
            stdin=data,
            check=True,
        )


if phase in ("all", "fresh"):
    with Database("final_coexistence", folder / "fresh") as db:
        text = checked(
            command(
                db,
                "-i",
                ",".join(addons + [regional]),
                "--without-demo",
                "--stop-after-init",
                "--test-enable",
                "--test-tags=" + ",".join("/" + name for name in addons + [regional]) + ",-/web",
            ),
            folder / "all-addons-fresh.log",
            allow_tracebacks=True,
        )
        assert_tests_ran(text, addons + [regional])

if phase in ("all", "legacy"):
    with (
        Database("legacy_release_restore", folder / "legacy") as db,
        tempfile.TemporaryDirectory(prefix="learning-release-restore-") as private,
    ):
        private = Path(private)
        old_modules = [
            "training_management",
            "training_management_sale",
            "training_management_survey",
            "training_management_website",
            "training_management_elearning",
            regional,
        ]
        checked(
            command(db, "-i", ",".join(old_modules), "--without-demo", "--stop-after-init", previous=True),
            folder / "legacy-install.log",
        )
        shell(
            db,
            "legacy-interactive-prepare",
            (ROOT / "ci/probe-module-relocation-prepare.py").read_text(),
            previous=True,
        )
        old_p09 = (TM / "tests/probes/p09_history.py").read_text().replace("tm_s01_test_p09", "tm_suite_test")
        shell(db, "legacy-p09-prepare", old_p09, previous=True, phase="P09_PHASE=baseline")
        mock_probe = (TM / "tests/probes/j1_mock_tm_history.py").read_text().replace("tm_s01_test_p09", "tm_suite_test")
        shell(db, "legacy-mock-prepare", mock_probe, previous=True, phase="J1_RUNTIME_PHASE=prepare")
        preservation = (ROOT / "ci/probe-legacy-release.py").read_text()
        shell(db, "legacy-snapshot", preservation, previous=True)
        old_archive = private / "before"
        old_archive.mkdir()
        old_dump, old_files = backup(db, old_archive)
        relocation = (TM / "tools/relocate_modules.py").read_text() + "\nenv.cr.commit()\n"
        shell(db, "legacy-relocate", relocation, previous=True)
        checked(
            command(
                db,
                "-u",
                "training_management,training_management_sale,training_management_survey,training_management_interactive,"
                + regional,
                "-i",
                "training_catalog,training_interactive,training_mock_exam,training_elearning,training_elearning_sale,training_elearning_survey",
                "--without-demo",
                "--stop-after-init",
            ),
            folder / "legacy-upgrade.log",
        )
        shell(db, "legacy-preserved", preservation)
        # Runtime verification may finish/restart attempts; isolate those checks
        # in a rolled-back transaction so later preservation checks remain strict.
        verify_mock = mock_probe.replace("env.cr.commit()", "env.cr.rollback()")
        shell(db, "legacy-mock-preserved", verify_mock, phase="J1_RUNTIME_PHASE=verify")
        shell(db, "relocation-idempotent", relocation)
        checked(command(db, "-u", ",".join(addons + [regional]), "--stop-after-init"), folder / "repeat-upgrade.log")
        shell(db, "repeat-preserved", preservation)
        current_archive = private / "after"
        current_archive.mkdir()
        current_dump, current_files = backup(db, current_archive)
        restore(db, current_dump, current_files, "tm_suite_restored")
        shell(db, "restored-current-preserved", preservation, database="tm_suite_restored")
        restored_mock = verify_mock.replace("tm_suite_test", "tm_suite_restored")
        shell(db, "restored-current-mock", restored_mock, database="tm_suite_restored", phase="J1_RUNTIME_PHASE=verify")
        restore(db, old_dump, old_files, "tm_suite_rollback")
        shell(db, "restored-rollback-preserved", preservation, previous=True, database="tm_suite_rollback")
        rollback_mock = verify_mock.replace("tm_suite_test", "tm_suite_rollback")
        rollback_mock = rollback_mock.replace(
            'assert not any(attempts.mapped("mock_context_key")), "No context identity should be invented on old evidence"',
            'assert "mock_context_key" not in attempts._fields or not any(attempts.mapped("mock_context_key"))',
        )
        rollback_mock = rollback_mock.replace(
            'fresh.mock_context_key == "training.enrollment:%s" % saved["enrollment"]',
            '("mock_context_key" not in fresh._fields or fresh.mock_context_key == "training.enrollment:%s" % saved["enrollment"])',
        )
        shell(
            db,
            "restored-rollback-mock",
            rollback_mock,
            previous=True,
            database="tm_suite_rollback",
            phase="J1_RUNTIME_PHASE=verify",
        )
(folder / "success.json").write_text(
    json.dumps(
        {
            "qualified_phase": phase,
            "all_target_addons": addons if phase in ("all", "fresh") else [],
            "optional_regional_integration": regional,
            "legacy_release": compatibility["legacy_release_baseline"],
            "original_business_columns_preserved": phase in ("all", "legacy"),
            "native_exam_and_interactive_evidence_preserved": phase in ("all", "legacy"),
            "current_database_and_filestore_restored": phase in ("all", "legacy"),
            "legacy_database_and_filestore_rollback_restored": phase in ("all", "legacy"),
        }
    )
    + "\n"
)
