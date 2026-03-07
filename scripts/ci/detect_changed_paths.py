#!/usr/bin/env python3
import json, subprocess, sys
mode = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == '--mode' else 'manual'
try:
    out = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], text=True)
    paths = [p for p in out.splitlines() if p.strip()]
except Exception:
    paths = []
print(json.dumps({'mode': mode, 'paths': paths}, indent=2))
