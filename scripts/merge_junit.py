from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path

JUNIT_DIR = Path("test_reports/junit")
OUT = JUNIT_DIR / "all.xml"

def iter_testcases(path: Path):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return
    if root.tag == "testsuite":
        yield root
    elif root.tag == "testsuites":
        for ts in root.findall("testsuite"):
            yield ts

def main():
    suites = []
    for p in sorted(JUNIT_DIR.glob("*.xml")):
        if p.name == "all.xml":
            continue
        for ts in iter_testcases(p):
            suites.append(ts)

    all_ts = ET.Element("testsuite", attrib={
        "name": "all", "tests": "0", "failures": "0", "errors": "0", "skipped": "0", "time": "0.0"
    })

   # accumulate
    totals = {"tests":0, "failures":0, "errors":0, "skipped":0, "time":0.0}
    for ts in suites:
        for case in ts.findall("testcase"):
            all_ts.append(case)
        for k in totals:
            v = ts.attrib.get(k)
            if v is None: 
                continue
            totals[k] += float(v) if k == "time" else int(v)
    for k,v in totals.items():
        all_ts.attrib[k] = f"{v}"

    tree = ET.ElementTree(all_ts)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tree.write(OUT, encoding="utf-8", xml_declaration=True)
    print(f"merged {len(suites)} suites -> {OUT}")

if __name__ == "__main__":
    main()
