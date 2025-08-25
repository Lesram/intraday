from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter

JUNIT_DIR = Path("test_reports/junit")
COV_XML = Path("test_reports/coverage.xml")

def load_suites():
    all_xml = JUNIT_DIR / "all.xml"
    suites = []
    def iter_suites(p: Path):
        r = ET.parse(p).getroot()
        if r.tag == "testsuite":
            return [r]
        if r.tag == "testsuites":
            return r.findall("testsuite")
        return []
    if all_xml.exists():
        suites = iter_suites(all_xml)
    else:
        for p in sorted(JUNIT_DIR.glob("*.xml")):
            if p.name == "all.xml": 
                continue
            try:
                suites.extend(iter_suites(p))
            except ET.ParseError:
                pass
    return suites

def summarize_junit():
    suites = load_suites()
    total=fail=err=skip=0
    fails=[]
    hist=Counter()

    for ts in suites:
        total += int(ts.attrib.get("tests", 0))
        fail  += int(ts.attrib.get("failures", 0))
        err   += int(ts.attrib.get("errors", 0))
        skip  += int(ts.attrib.get("skipped", 0))
        for case in ts.findall("testcase"):
            f = case.find("failure") or case.find("error")
            if f is not None:
                cls = case.attrib.get("classname","")
                nm  = case.attrib.get("name","")
                msg = (f.attrib.get("message") or "").splitlines()[0]
                fails.append((cls,nm,msg))
                hist[cls] += 1

    print("=== JUNIT SUMMARY ===")
    print(f"tests={total} failures={fail} errors={err} skipped={skip}")
    if fails:
        print("\nTop failures (up to 10):")
        for cls,nm,msg in fails[:10]:
            print(f" - {cls}::{nm} :: {msg}")
    if hist:
        print("\nFailure histogram by class (top 10):")
        for k,v in hist.most_common(10):
            print(f" - {k}: {v}")

def summarize_coverage():
    if not COV_XML.exists():
        print("\nNo coverage.xml found.")
        return
    root = ET.parse(COV_XML).getroot()
    line_rate = float(root.attrib.get("line-rate",0.0))*100.0
    print(f"\n=== COVERAGE SUMMARY ===\nOverall line coverage: {line_rate:.2f}%")
    miss_by_file=[]
    for pkg in root.iter("package"):
        for cls in pkg.iter("class"):
            fn = cls.attrib.get("filename","")
            lines = cls.find("lines")
            if lines is None: 
                continue
            total=hit=0
            for ln in lines:
                total+=1
                if int(ln.attrib.get("hits","0"))>0: hit+=1
            miss = total-hit
            miss_by_file.append((miss, fn, total))
    miss_by_file.sort(reverse=True)
    print("\nTop 10 files by missed lines:")
    for miss, fn, total in miss_by_file[:10]:
        print(f" - {fn}: missed {miss} / {total}")
    print("\nFiles with 0% coverage (selected areas):")
    shown=0
    for miss, fn, total in miss_by_file:
        if total>0 and miss==total and fn.startswith(("backend/api","backend/mlops","backend/models")):
            print(f" - {fn}")
            shown+=1
            if shown>=10: break

if __name__ == "__main__":
    summarize_junit()
    summarize_coverage()
