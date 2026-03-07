#!/usr/bin/env python3
import json, os, subprocess, pathlib
art = pathlib.Path('artifacts')
art.mkdir(exist_ok=True)

def sh(cmd):
    try:
        return subprocess.check_output(cmd, text=True).strip()
    except Exception:
        return ''

report = {
    'task_id': os.environ.get('INTRA_TASK_ID', ''),
    'summary': os.environ.get('INTRA_TASK_SUMMARY', ''),
    'files_changed': sh(['git', 'diff', '--name-only', 'HEAD']).splitlines(),
    'commands': [],
    'tests_passed': [],
    'tests_failed': [],
    'runtime_behavior_changed': [],
    'docs_updated': [],
    'risks': [],
    'follow_ups': []
}
(art / 'task-report.json').write_text(json.dumps(report, indent=2))
print(str(art / 'task-report.json'))
