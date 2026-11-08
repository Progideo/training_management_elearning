"""Manual local qualification, fictional data only. This script does not call CI."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "odoo@sha256:61e3c71b0503c5f658e604c3e340bede20b97d05f726179fa006eae50a32fd23"
POSTGRES = "postgres@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336"
TAGS = "/training_elearning_resources,/training_elearning:TestNativeLessons,/training_elearning:TestNativeLessonPortal,/training_elearning:TestActivityAvailability,-/web"


FULL_MODULES = ("training_management", "training_management_sale", "training_management_survey",
                "training_management_interactive", "sale_invoice_address_fiscal", "training_catalog",
                "training_interactive", "training_mock_exam", "training_elearning", "training_elearning_sale",
                "training_elearning_survey", "training_elearning_resources")


def source_hash(folder):
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(str(path.relative_to(folder)).encode() + b"\0" +
                      hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n")
    return digest.hexdigest()


def qualify(addons, output, full=False):
    sources = {"resource_addon_sha256": source_hash(ROOT / "addons/training_elearning_resources"),
               "shared_addons_sha256": source_hash(addons)}
    output.mkdir(parents=True, exist_ok=False)
    data = output / "data"
    data.mkdir(mode=0o777)
    data.chmod(0o777)
    name = "learning-resources-" + uuid.uuid4().hex[:12]
    pg = name + "-pg"
    call = lambda args, **kw: subprocess.run(args, check=True, **kw)
    call(["docker", "network", "create", "--internal", name], stdout=subprocess.DEVNULL)
    try:
        call(["docker", "run", "-d", "--pull", "never", "--name", pg, "--network", name, "--memory", "1g", "--cpus", "1",
              "-e", "POSTGRES_USER=fictional", "-e", "POSTGRES_PASSWORD=fictional-only",
              "-e", "POSTGRES_DB=resources_fictional", POSTGRES], stdout=subprocess.DEVNULL)
        for _ in range(60):
            if subprocess.run(["docker", "exec", pg, "pg_isready", "-U", "fictional", "-d", "resources_fictional"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Disposable PostgreSQL unavailable")
        docker = ["docker", "run", "--rm", "--pull", "never", "-i", "--name", name + "-odoo", "--network", name,
                  "--cpus", "2", "--memory", "3g", "--pids-limit", "256", "--security-opt", "no-new-privileges:true",
                  "-e", "HOST=" + pg, "-e", "USER=fictional", "-e", "PASSWORD=fictional-only",
                  "-e", "PYTHONDONTWRITEBYTECODE=1", "-v", str(data) + ":/var/lib/odoo",
                  "-v", str(ROOT / "addons") + ":/mnt/elearning-addons:ro",
                  "-v", str(addons) + ":/mnt/shared-addons:ro", "-v", str(ROOT / "bench") + ":/mnt/bench:ro"]
        flags = ["-d", "resources_fictional", "--db-filter=^resources_fictional$",
                 "--addons-path=/mnt/elearning-addons,/mnt/shared-addons", "--workers=0", "--max-cron-threads=0",
                 "--smtp=127.0.0.1", "--smtp-port=1", "--stop-after-init", "--without-demo"]

        def execute(label, args, phase=None):
            command = docker + (["-e", "RESOURCE_PROBE_PHASE=" + phase] if phase else []) + [IMAGE, "odoo"] + args
            with (output / (label + ".log")).open("w") as log:
                result = subprocess.run(command, stdout=log, stderr=log,
                    input="exec(open('/mnt/bench/probe-resources.py').read())" if phase else None, text=True)
            text = (output / (label + ".log")).read_text(errors="replace")
            if result.returncode or re.search(r" [1-9][0-9]* failed,| [1-9][0-9]* error\(s\)| CRITICAL ", text):
                raise RuntimeError(label + " failed; inspect " + str(output / (label + ".log")))
            if phase:
                assert "RESOURCE_PROBE=" in text
            else:
                assert "0 failed, 0 error(s)" in text
                assert "Starting TestResourcesHTTP." in text and "Starting TestResources." in text
            print(label + ": passed", flush=True)

        modules = ",".join(FULL_MODULES) if full else "training_elearning_resources"
        tags = TAGS + (",/training_elearning_survey:TestAutonomousExams,/training_elearning_sale:TestAutonomousSales,/training_elearning_sale:TestSoldVersions" if full else "")
        for label, flag in (("install", "-i"), ("update", "-u")):
            execute(label, flags + [flag, modules, "--test-enable", "--test-tags=" + tags])
            phase = "prepare" if label == "install" else "preserved"
            execute(phase, ["shell", *flags, "--no-http"], phase)
        # Real independent transactions, then physical dump + filestore restore.
        execute("concurrency", ["shell", *flags, "--no-http"], "concurrency")
        with (output / "fictional.dump").open("wb") as dump:
            call(["docker", "exec", pg, "pg_dump", "-Fc", "-U", "fictional", "resources_fictional"], stdout=dump)
        shutil.copytree(data, output / "filestore-backup")
        call(["docker", "exec", pg, "dropdb", "-U", "fictional", "resources_fictional"])
        call(["docker", "exec", pg, "createdb", "-U", "fictional", "resources_fictional"])
        with (output / "fictional.dump").open("rb") as dump:
            call(["docker", "exec", "-i", pg, "pg_restore", "--single-transaction", "-U", "fictional", "-d", "resources_fictional"], stdin=dump)
        shutil.rmtree(data)
        shutil.copytree(output / "filestore-backup", data)
        data.chmod(0o777)
        execute("restored", ["shell", *flags, "--no-http"], "preserved")
        (output / "success.json").write_text(json.dumps({"fictional_only": True, "image": IMAGE, "full_composition": full,
            "postgres": POSTGRES, "phases": ["install", "prepare", "update", "preserved", "concurrency", "restored"],
            **sources, "dump_sha256": hashlib.sha256((output / "fictional.dump").read_bytes()).hexdigest()}, indent=2))
    finally:
        subprocess.run(["docker", "rm", "-f", "-v", name + "-odoo", pg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["docker", "network", "rm", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-addons", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full-composition", action="store_true")
    args = parser.parse_args()
    qualify(args.shared_addons.resolve(), args.output.resolve(), args.full_composition)
