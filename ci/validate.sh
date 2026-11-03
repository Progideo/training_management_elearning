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
head = subprocess.check_output(['git', '-C', str(tm), 'rev-parse', 'HEAD'], text=True).strip()
# TM_HEAD_CHECK: daily contract check against the current Training Management, never a release qualification.
assert os.environ.get('TM_HEAD_CHECK') == '1' or head == c['training_management']['commit']
print('Training Management', head, 'pinned', c['training_management']['commit'])
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
  modules=training_management_elearning
  if [[ "$phase" == update ]]; then
    flag=-u
    modules=training_catalog,training_interactive,training_management,training_management_survey,training_management_elearning
  fi
  ./bench/e01/run run --rm -T odoo odoo -d elearning_ci \
    --addons-path=/mnt/extra-addons,/mnt/qualification-addons \
    --without-demo=all --workers=0 --max-cron-threads=0 \
    "$flag" "$modules" --test-enable \
    --test-tags "$(cat bench/review/test-tags)" --stop-after-init \
    2>&1 | tee "ci-results/$phase.log"
  python3 ci/check_results.py "ci-results/$phase.log"
done
# Website rewrites portal layouts: the participant routes must also work on this stack.
./bench/e01/run run --rm -T odoo odoo -d elearning_ci_website \
  --addons-path=/mnt/extra-addons,/mnt/qualification-addons \
  --without-demo=all --workers=0 --max-cron-threads=0 \
  -i website,training_management_website,training_management_elearning --test-enable \
  --test-tags /training_management_elearning --stop-after-init \
  2>&1 | tee ci-results/website.log
python3 ci/check_results.py ci-results/website.log
