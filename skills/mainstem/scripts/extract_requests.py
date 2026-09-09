#!/usr/bin/env python3
"""Pull DATA.requests out of a downloaded control-center HTML into requests.json."""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

cfg = load_config()
html = open(sys.argv[1]).read()
m = re.search(r'const DATA = (\{.*?\});\nDATA\.requests', html, re.S)
if not m:
    sys.exit("no `const DATA = {...}; DATA.requests` block found in %s — not a control-center page?" % sys.argv[1])
data = json.loads(m.group(1).replace('<\\/', '</'))
out = os.path.join(cfg["dataDir"], 'requests.json')
json.dump(data.get('requests', []), open(out, 'w'), indent=1, ensure_ascii=False)
print(out, len(data.get('requests', [])), 'requests;', sum(1 for r in data.get('requests', []) if r.get('status')=='pending'), 'pending')
