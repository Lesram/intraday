"""Score locked prospective Tier 1 diagnostic alarms at MONTHLY cadence.

Use a separately downloaded, dated USREC CSV (--outcomes). Only the final
acquired reading in each closed UTC month defines its state. Open months and
missing/failed months cannot establish a crossing. Historical snapshot runs are
excluded. This deliberately does not assign monthly study accuracy to every
transient native-frequency operational flag. Outcome labels remain revisable.
"""
from pathlib import Path
import argparse,csv,hashlib,json
from datetime import datetime,timezone
import pandas as pd
import monitor


def utc_naive(value):
    t=pd.Timestamp(value)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def score(readings, outcomes, asof=None):
    asof=utc_naive(asof if asof is not None else datetime.now(timezone.utc))
    if outcomes is not None and not outcomes.dropna().isin([0,1]).all():
        raise ValueError("USREC must contain only 0, 1, or missing values")
    monthly={}
    for item in readings:
        if item.get("mode")!="live":continue
        # Observation/as-of dates cannot substitute for proof of acquisition.
        if not item.get("generated_at"):continue
        acquired=utc_naive(item["generated_at"])
        month=acquired.to_period("M")
        if acquired>asof or month.end_time>asof:continue
        key=(item["spec_version"],month)
        old=monthly.get(key)
        if old is None or acquired>old[0]:monthly[key]=(acquired,item)
    rows=[]; active={}; last_alarm={}
    for (version,origin),(acquired,snapshot) in sorted(monthly.items(),key=lambda kv:(kv[0][1],kv[0][0])):
        if snapshot.get("status")!="validated":
            active={k:v for k,v in active.items() if k[0]!=version}
            continue
        for indicator in snapshot["indicators"]:
            if indicator["tier"]!=1:continue
            ident=(version,indicator["id"])
            if indicator["status"] not in ("below","crossed"):
                active.pop(ident,None)
                continue
            crossed=indicator["status"]=="crossed"
            previous=active.get(ident)
            # A first high, a missing month, or a failed reading establishes a new
            # baseline; none proves a new false->true threshold crossing.
            new=previous is not None and previous[1]==origin-1 and crossed and not previous[0]
            active[ident]=(crossed,origin)
            if not new:continue
            if ident in last_alarm and origin.ordinal-last_alarm[ident].ordinal<12:continue
            last_alarm[ident]=origin
            end=origin+12
            window=pd.period_range(origin,end,freq="M")
            observed=outcomes.reindex(window) if outcomes is not None else pd.Series(index=window,dtype=float)
            mature=end.end_time<=asof and observed.notna().all()
            hits=observed[observed==1]
            rows.append({"indicator":indicator["id"],"spec_version":version,"alarm_asof":str(acquired.date()),"signal_month":str(origin),"acquired_at":acquired.isoformat()+"Z","scored_asof":asof.isoformat()+"Z","target":"recession present or onset within 12 calendar months","horizon_end":str(end.end_time.date()),"status":"hit" if mature and len(hits) else "false_alarm" if mature else "pending","lead_months":hits.index[0].ordinal-origin.ordinal if mature and len(hits) else "","note":"Monthly final acquired state; exact acquisition timing can differ from the historical study's coarse release lags. Diagnostic association, not a forecast. USREC outcomes are retrospective and may revise; re-score with dated label receipts."})
    return rows


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--outcomes",type=Path);p.add_argument("--as-of",help="Scoring timestamp; defaults to current UTC time");p.add_argument("--output",type=Path,default=monitor.REVIEW/"pipeline/output/prospective_scorecard.csv");a=p.parse_args()
    # Include failed attempts so a failed final monthly observation breaks the
    # crossing chain. Older archives with readings only remain supported.
    files=set((monitor.REVIEW/"pipeline/readings").glob("*.json"))|set((monitor.REVIEW/"pipeline/attempts").glob("*.json"))
    readings=[json.loads(f.read_text()) for f in sorted(files)]
    outcome=None
    if a.outcomes:
        s=monitor.parse_csv(a.outcomes.read_text(),"USREC");outcome=monitor.monthly(s)
        if not outcome.dropna().isin([0,1]).all():raise ValueError("USREC must contain only 0, 1, or missing values")
    rows=score(readings,outcome,a.as_of)
    target=monitor.safe_path(a.output);target.parent.mkdir(exist_ok=True,parents=True)
    fields=["indicator","spec_version","alarm_asof","signal_month","acquired_at","scored_asof","target","horizon_end","status","lead_months","note"]
    with target.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    monitor.write_json(target.with_suffix(".metadata.json"),{"scored_at":datetime.now(timezone.utc).isoformat(),"scoring_as_of":a.as_of or "current UTC","outcome_file":str(a.outcomes) if a.outcomes else None,"outcome_sha256":hashlib.sha256(a.outcomes.read_bytes()).hexdigest() if a.outcomes else None,"outcome_published_at":None,"outcome_acquired_at":None,"outcome_timestamp_note":"File ingestion time is the scoring time; original publisher/retrieval times are not supplied.","sampling":"Final acquired state in each closed UTC month; consecutive observed months required","labels":"Retrospective USREC; scored labels may revise"})
    print(json.dumps({"eligible_prospective_alarms":len(rows),"pending":sum(r['status']=='pending' for r in rows),"output":str(target)}))
