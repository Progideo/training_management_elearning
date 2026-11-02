#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${TM_ADDONS_DIR:?Required}"
: "${LMS_SECRET_DIR:?Required}"
: "${LMS_COMPOSE_PROJECT:?Required isolated project name}"
python3 - <<'CHECK'
import ast, json, os, pathlib, subprocess
c = json.load(open('compatibility.json'))
tm = pathlib.Path(os.environ['TM_ADDONS_DIR']).resolve().parent
assert subprocess.check_output(['git', '-C', str(tm), 'rev-parse', 'HEAD'], text=True).strip() == c['training_management']['commit']
assert not subprocess.check_output(['git', '-C', str(tm), 'status', '--porcelain']).strip()
m = ast.literal_eval(pathlib.Path('addons/training_management_elearning/__manifest__.py').read_text())
assert m['version'] == c['elearning_version']
assert m['depends'] == c['required_addons']
assert c['odoo_image'] in pathlib.Path('bench/e01/compose.yaml').read_text()
CHECK
mkdir -p ci-results
# Refuse to reuse a previous project or an existing secret directory.
if [[ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$LMS_COMPOSE_PROJECT")" || -n "$(docker volume ls -q --filter "label=com.docker.compose.project=$LMS_COMPOSE_PROJECT")" ]]; then
  echo 'Project already exists; choose a fresh name.' >&2
  exit 1
fi
mkdir -m 700 "$LMS_SECRET_DIR"
python3 - <<'SECRET'
import os, pathlib, secrets
p = pathlib.Path(os.environ['LMS_SECRET_DIR']) / 'db_password'
p.write_text(secrets.token_hex(32))
p.chmod(0o644)  # Container processes can read the mounted file; parent is 0700.
SECRET
cleanup() {
  result=$?
  trap - EXIT
  ./bench/e01/run logs --no-color > ci-results/services.log 2>&1 || true
  ./bench/e01/run down -v --remove-orphans >> ci-results/cleanup.log 2>&1 || result=1
  rm -f "$LMS_SECRET_DIR/db_password"
  rmdir "$LMS_SECRET_DIR" || result=1
  exit "$result"
}
trap cleanup EXIT
./bench/e01/run up -d --wait odb
for phase in install update; do
  flag=-i
  [[ "$phase" == update ]] && flag=-u
  ./bench/e01/run run --rm -T odoo odoo -d elearning_ci \
    --addons-path=/mnt/extra-addons,/mnt/qualification-addons \
    --without-demo=all --workers=0 --max-cron-threads=0 \
    "$flag" training_management_elearning --test-enable \
    --test-tags "$(cat bench/review/test-tags)" --stop-after-init \
    2>&1 | tee "ci-results/$phase.log"
  python3 ci/check_results.py "ci-results/$phase.log"
done
