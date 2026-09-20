"""Refresh measurements, report and the same dashboard; propagate failures loudly."""
from pathlib import Path
import argparse,csv,os,subprocess,sys
from datetime import datetime,timezone
import monitor

def main():
    p=argparse.ArgumentParser();p.add_argument("--mode",choices=["snapshot","live"],default="snapshot");p.add_argument("--as-of");p.add_argument("--outcomes",type=Path,help="Optional dated USREC CSV for prospective alarm outcomes");p.add_argument("--node",default=os.environ.get("MACRO_NODE","node"));p.add_argument("--data-plugin-root",type=Path,default=Path.home()/".codex/plugins/cache/openai-curated-remote/data-analytics/1.0.9");a=p.parse_args()
    asof=a.as_of or (datetime.now(timezone.utc).date().isoformat() if a.mode=="live" else "2026-09-18")
    status=monitor.main(["--mode",a.mode,"--as-of",asof])
    root=monitor.REVIEW;app=root/"dashboard_app";tool=a.data_plugin_root/"scripts/data-app.mjs"
    subprocess.run([sys.executable,str(root/"pipeline/to_app.py"),"--output",str(app/"src/data.json"),"--complete"],check=True)
    if not tool.is_file():
        print("Dashboard compiler unavailable; report/attempt saved but dashboard NOT refreshed. Supply --data-plugin-root.",file=sys.stderr)
        return 3
    subprocess.run([a.node,str(tool),"build","--project-dir",str(app),"--separate-data"],check=True)
    export=app/".data-app-offline/exports/dashboard.html"
    subprocess.run([a.node,str(tool),"export-offline","--project-dir",str(app),"--output",str(export)],check=True)
    # User explicitly requested a portable standalone artifact in review/.
    (root/"dashboard.html").write_bytes(export.read_bytes())
    scorer=[sys.executable,str(root/"pipeline/score_archive.py")]
    if a.outcomes:scorer.extend(["--outcomes",str(a.outcomes)])
    subprocess.run(scorer,check=True)
    with (root/"pipeline/output/prospective_scorecard.csv").open() as f:alarms=list(csv.DictReader(f))
    counts={s:sum(r["status"]==s for r in alarms) for s in ["hit","false_alarm","pending"]}
    report=root/"pipeline/output"/("report.md" if status==0 else "failed_report.md")
    with report.open("a") as f:
        f.write("\n## Archived alarm review\n\n")
        f.write(f"Eligible prospective episodes: {len(alarms)}. Mature hits: {counts['hit']}; mature false alarms: {counts['false_alarm']}; unresolved: {counts['pending']}.\n\n")
        f.write("Outcome labels supplied and hashed in prospective_scorecard.metadata.json.\n" if a.outcomes else "No outcome-label file supplied: no new historical success is inferred. Use --outcomes with a dated USREC CSV when scoring matured alarms.\n")
        f.write("Snapshot reproductions are excluded. First-high readings and gaps do not create proven crossings; full calendar horizons and outcome coverage are required. Detailed rows: prospective_scorecard.csv.\n")
    return status

if __name__=="__main__":raise SystemExit(main())
