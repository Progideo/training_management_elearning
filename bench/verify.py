"""Compare persisted checkpoints and the read-only business checkout."""
import os
import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
evidence = root / 'evidence'
checkpoints = []
for name in ('before-update', 'after-update-1', 'after-update-2'):
    lines = (evidence / (name + '.log')).read_text().splitlines()
    payloads = [line.removeprefix('E00_CHECKPOINT=') for line in lines if line.startswith('E00_CHECKPOINT=')]
    assert len(payloads) == 1, name
    value = json.loads(payloads[0])
    checkpoints.append(value)
    (evidence / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n')
assert checkpoints[0] == checkpoints[1] == checkpoints[2], 'Persistent history changed'
tm = Path(os.environ['TM_ADDONS_DIR']).resolve().parent
files = subprocess.check_output(['git', '-C', str(tm), 'ls-files', '-z']).decode().split('\0')
after = {f: hashlib.sha256((tm / f).read_bytes()).hexdigest() for f in files if (tm / f).is_file()}
assert after == json.loads((evidence / 'tm-before.json').read_text()), 'TM changed'
assert not subprocess.check_output(['git', '-C', str(tm), 'status', '--porcelain']).strip()
assert subprocess.check_output(['git', '-C', str(tm), 'rev-parse', 'HEAD']).decode().strip() == '9c9fdcd0bff5ce282602b819fe7165fa6dd4e2d5'
(evidence / 'tm-after.json').write_text(json.dumps(after, indent=2) + '\n')
print(f'PASS: 3 identical checkpoints; {len(after)} tracked TM files unchanged; clean TM checkout and identical HEAD.')
