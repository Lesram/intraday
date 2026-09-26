"""Convert a validated or failed monitor attempt to the portable dashboard snapshot."""
from pathlib import Path
import argparse, json

ROOT=Path(__file__).resolve().parents[1]

def convert(snapshot):
    queries={}
    for row in snapshot["indicators"]:
        source_ids=list(row.get("source_observations",{}))
        queries[row["id"]]={"rows":[row],"source":{"type":"file" if snapshot["mode"]=="snapshot" else "api","name":"Supplied FRED captures" if snapshot["mode"]=="snapshot" else "FRED CSV refresh","executedAt":snapshot["generated_at"],"files":(["data/raw/fred_bundle_2026-09-19.json","data/raw/fred_bundle2_2026-09-19.json"] if snapshot["mode"]=="snapshot" else []),"freshness":snapshot["cutoff_note"],"evidenceFlow":[{"title":"Read source series","detail":" | ".join(source_ids) or row["source_url"]},{"title":"Transform","detail":row["formula"]},{"title":"Validate","detail":row["error"] or "Schema, calendar alignment, missing-input and freshness checks; details in pipeline/output/attempt.json"}],"links":[{"label":sid,"url":"https://fred.stlouisfed.org/series/"+sid} for sid in source_ids]},"methods":[{"language":"text","code":row["formula"]}],"metricDefinitions":[{"label":row["name"],"definition":row["formula"],"componentIds":["signal-"+row["id"],"history-"+row["id"]]}],"caveats":[row["base_rate"],row["false_positive_rate"]]}
        queries["history_"+row["id"]]={"rows":row["history"],"source":queries[row["id"]]["source"],"methods":queries[row["id"]]["methods"],"caveats":["Last24 native observations, not equal time spans across indicators; missing values remain gaps."]}
    queries["monitor_status"]={"rows":[{"as_of":snapshot["as_of"],"mode":snapshot["mode"],"status":snapshot["status"],"regime":snapshot["regime"],"changed_indicators":len(snapshot["changes"])}],"source":{"type":"derived","name":"Macro monitor version "+snapshot["spec_version"],"files":["pipeline/output/attempt.json"]}}
    return {"surface":"dashboard","id":"macro-monitor-review-002","title":"Macro conditions monitor","generatedAt":snapshot["generated_at"],"status":"reviewed","buildStatus":"creating","filters":[],"queries":queries,"monitor":snapshot}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--input",type=Path,default=ROOT/"pipeline/output/attempt.json");p.add_argument("--output",type=Path,default=ROOT/"pipeline/app_snapshot.json");p.add_argument("--complete",action="store_true");a=p.parse_args()
    if ROOT not in a.output.resolve().parents:raise ValueError("Output outside review/")
    data=convert(json.loads(a.input.read_text()))
    if a.complete:data["buildStatus"]="complete"
    existing=ROOT/"dashboard_app/src/data.json"
    if existing.exists():data["id"]=json.loads(existing.read_text())["id"]
    a.output.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
