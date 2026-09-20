"""Select eight verdict-covered claims from each of nine INPUT packages.
This script must run only after the Phase A/B hash seal is written.
The reviewer receives blind_claims.csv, never the original label mapping.
"""
from pathlib import Path
import csv,hashlib,json

ROOT=Path(__file__).resolve().parents[1]
MACRO=ROOT.parent
SEED="review002:2026-09-19:blind-second-reader:v1"

if not (ROOT/"LOG.md").exists() or not (ROOT/"artifacts/blind_seal.json").exists():
    raise SystemExit("Phase A/B seal required before reading prior verdicts")

verdicts={}
for p in sorted((MACRO/"verify/out").glob("V*/verdicts.csv")):
    for row in csv.DictReader(p.open()):
        if row["claim_id"] in verdicts:raise ValueError("Duplicate verdict claim_id")
        verdicts[row["claim_id"]]={**row,"verdict_package":p.parent.name}

samples=[]; originals=[]; design=[]
for p in sorted((MACRO/"verify/in").glob("V*.csv")):
    rows=[r for r in csv.DictReader(p.open()) if r["claim_id"] in verdicts]
    ranked=sorted(rows,key=lambda r:hashlib.sha256((SEED+":"+r["claim_id"]).encode()).hexdigest())
    selected=ranked[:8]
    if len(selected)<8:raise ValueError("Insufficient rows in "+p.name)
    design.append({"input_package":p.stem,"eligible":len(rows),"sampled":len(selected)})
    for row in selected:
        keep={k:row.get(k,"") for k in ["claim_id","channel","video_id","video_date","timestamp","claim_type","thesis_cluster","claim_text","data_cited","source_cited"]}
        keep["input_package"]=p.stem;samples.append(keep)
        originals.append({**verdicts[row["claim_id"]],"input_package":p.stem})

for name,rows in [("blind_claims.csv",samples),("original_labels_DO_NOT_OPEN_BEFORE_JUDGING.csv",originals)]:
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (ROOT/"phase_c"/name).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
(ROOT/"phase_c/blind_sampling_design.json").write_text(json.dumps({"seed":SEED,"sampling":"Stable SHA256 ranks; 8 covered claims per input package. Package-balanced sample; not prevalence-proportional.","packages":design,"n":len(samples),"blind_columns":"No old verdict, measured value, note, or verification plan supplied to second reader."},indent=2))
print(json.dumps({"sampled":len(samples),"packages":len(design)}))
