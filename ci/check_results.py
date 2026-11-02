"""Require an actual, nonempty successful Odoo test summary."""
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()
results = re.findall(r"(\d+) failed, (\d+) error\(s\) of (\d+) tests", text)
if not results or any(int(f) or int(e) or int(n) == 0 for f, e, n in results):
    raise SystemExit("Missing or failed Odoo test summary")
if re.search(r"(?:ERROR|CRITICAL).*odoo\.tests|Traceback \(most recent call last\)", text):
    raise SystemExit("Unexpected test error or traceback")
print("PASS: Odoo test summaries:", results)
