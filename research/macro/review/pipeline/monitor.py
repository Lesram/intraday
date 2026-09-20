"""Read-only macro monitoring. All writes stay inside the review directory.

Snapshot mode is a dated reproduction, never a live refresh. Live mode obtains
each source anew, records failures, and exits nonzero on any required failure.
No broker, order, platform config, credentials, or personalised trade logic.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import urllib.request
from datetime import datetime, timezone
import numpy as np
import pandas as pd

REVIEW = Path(__file__).resolve().parents[1]
MACRO = REVIEW.parent
VERSION = "002.2"
SOURCES = {
    "ICSA": ("weekly", 14), "SAHMREALTIME": ("monthly", 20),
    "BAA10Y": ("daily", 7), "NFCI": ("weekly", 14),
    "GS10": ("monthly", 20), "TB3MS": ("monthly", 20),
    "CPIAUCSL": ("monthly", 25), "CPILFESL": ("monthly", 25),
    "DCOILBRENTEU": ("daily", 10),
    "NCBEILQ027S": ("quarterly", 100), "GDP": ("quarterly", 100),
    "CPATAX": ("quarterly", 100),
}
# Monthly/quarterly numbers above are conservative calendar-day release grace
# periods AFTER the end of the next source observation, not maximum ages of a
# currently valid reading. Daily/weekly numbers remain observation-age limits.


def safe_path(path: Path) -> Path:
    path = path.resolve()
    if path != REVIEW and REVIEW not in path.parents:
        raise ValueError("Output must remain within review/")
    return path


def write_json(path: Path, payload):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def parse_csv(text: str, series_id: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    if len(df.columns) != 2 or not len(df):
        raise ValueError(f"{series_id}: expected nonempty date/value CSV")
    if series_id in SOURCES and df.columns[1] != series_id:
        raise ValueError(f"{series_id}: response contains unexpected series {df.columns[1]}")
    dates = pd.to_datetime(df.iloc[:, 0], errors="raise")
    values = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    missing = df.iloc[:, 1].isna() | df.iloc[:, 1].astype(str).str.strip().isin(["", "."])
    if (values.isna() & ~missing).any():
        raise ValueError(f"{series_id}: nonnumeric value is not a recognized missing-data marker")
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError(f"{series_id}: duplicate or unsorted observation dates")
    s = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(dates), name=series_id)
    if not np.isfinite(s.dropna()).all() or s.notna().sum() < 2:
        raise ValueError(f"{series_id}: invalid or insufficient observations")
    return s.dropna()


def monthly(s: pd.Series) -> pd.Series:
    out = s.groupby(s.index.to_period("M")).last()
    return out.reindex(pd.period_range(out.index.min(), out.index.max(), freq="M"))


def calendar_yoy(s: pd.Series) -> pd.Series:
    """Missing months remain missing; 12 means calendar months, not row positions."""
    s = monthly(s)
    return s.div(s.shift(12)).sub(1).mul(100)


def weekly_claims(s: pd.Series) -> pd.Series:
    # A missing week must not turn four observations into a five-week average.
    if not (s.index.dayofweek == 5).all():
        raise ValueError("ICSA: expected week-ending Saturday observations")
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="W-SAT"))
    avg = s.rolling(4, min_periods=4).mean()
    return avg.div(avg.rolling(52, min_periods=52).min()).sub(1).mul(100)


def derive(series: dict[str, pd.Series], asof=None) -> dict[str, pd.Series]:
    if asof is not None:
        cutoff = pd.Timestamp(asof)
        series = {sid: s[s.index <= cutoff] for sid, s in series.items()}
    out = {}
    if "ICSA" in series: out["claims_rise"] = weekly_claims(series["ICSA"])
    for key, sid in [("sahm", "SAHMREALTIME"), ("credit_level", "BAA10Y"), ("nfci", "NFCI"), ("brent", "DCOILBRENTEU")]:
        if sid in series: out[key] = series[sid]
    if "BAA10Y" in series: out["credit_change"] = monthly(series["BAA10Y"]).diff(3)
    if {"GS10", "TB3MS"} <= series.keys(): out["curve"] = monthly(series["GS10"]) - monthly(series["TB3MS"])
    for key, sid in [("inflation", "CPIAUCSL"), ("core_inflation", "CPILFESL")]:
        if sid in series: out[key] = calendar_yoy(series[sid])
    if "inflation" in out: out["inflation_acceleration"] = out["inflation"].diff(12)
    if {"NCBEILQ027S", "GDP"} <= series.keys(): out["equities_gdp"] = series["NCBEILQ027S"].div(1000).div(series["GDP"]).mul(100)
    if {"CPATAX", "GDP"} <= series.keys(): out["profit_share"] = series["CPATAX"].div(series["GDP"]).mul(100)
    if asof is not None:
        # Partial daily data must never masquerade as completed month-end signals.
        cutoff=pd.Timestamp(asof)
        out={k:s[s.index.to_timestamp(how="end").normalize()<=cutoff] if isinstance(s.index,pd.PeriodIndex) else s for k,s in out.items()}
    return out


def period_end(date, frequency):
    date = pd.Timestamp(date)
    return date.to_period({"monthly":"M", "quarterly":"Q"}[frequency]).end_time.normalize() if frequency in ("monthly","quarterly") else date


def source_health(s, sid, asof):
    freq, limit = SOURCES[sid]
    s = s[s.index <= asof]
    if s.empty: raise ValueError(f"{sid}: no data at or before as-of date")
    observation = s.index[-1]
    end = period_end(observation, freq)
    age = int((asof - end).days)
    if age < 0: raise ValueError(f"{sid}: incomplete observation period {end.date()} exceeds as-of")
    if freq in ("monthly", "quarterly"):
        next_end = (observation.to_period("M" if freq == "monthly" else "Q") + 1).end_time.normalize()
        deadline = next_end + pd.Timedelta(days=limit)
        max_age = int((deadline - end).days)
        basis = f"Next {freq} observation period end plus {limit} calendar days; conservative release assumption, not an exact release calendar"
    else:
        deadline = end + pd.Timedelta(days=limit)
        max_age = limit
        basis = f"Latest observed {freq} date plus {limit} calendar days, allowing ordinary release delay and holidays"
    if asof > deadline:
        raise ValueError(f"{sid}: stale; next observation expected by {deadline.date()} (age {age}d, limit {max_age}d)")
    return {"observation_date":str(observation.date()),"period_end":str(end.date()),"age_days":age,"max_age_days":max_age,"frequency":freq,"first_observation":str(s.index[0].date()),"next_observation_due_by":str(deadline.date()),"freshness_basis":basis,"published_at":None}


def load_sources(mode, asof):
    raw, receipts, errors = {}, {}, {}
    captured = datetime.now(timezone.utc).isoformat()
    if mode == "snapshot":
        if asof < pd.Timestamp("2026-09-18"):
            raise ValueError("Snapshot contains 2026-09-19 revisions; earlier pseudo-real-time runs prohibited")
        for file in sorted((MACRO/"data/raw").glob("fred_bundle*_2026-09-19.json")):
            for sid, txt in json.loads(file.read_text())["series"].items():
                if sid in SOURCES:
                    if sid in raw and raw[sid] != txt:
                        raise ValueError(f"Conflicting bundled versions of {sid}")
                    raw[sid] = txt
                    receipts[sid] = {"source_file":str(file.relative_to(MACRO)),"retrieved_at":"2026-09-19 (supplied capture)","acquired_at":"2026-09-19","acquisition_precision":"day only; supplied capture","url":f"https://fred.stlouisfed.org/series/{sid}"}
    else:
        def fetch(sid):
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
            req = urllib.request.Request(url, headers={"User-Agent":"MacroResearchMonitor/002"})
            with urllib.request.urlopen(req, timeout=25) as response:
                data = response.read(15_000_001)
            if len(data) > 15_000_000: raise ValueError("Response exceeds size limit")
            return data.decode("utf-8-sig"), url
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(fetch,sid):sid for sid in SOURCES}
            for job in concurrent.futures.as_completed(jobs):
                sid = jobs[job]
                try:
                    txt,url = job.result(); raw[sid] = txt
                    acquired = datetime.now(timezone.utc).isoformat()
                    receipts[sid] = {"url":url,"retrieved_at":acquired,"acquired_at":acquired,"acquisition_precision":"timestamp UTC"}
                except Exception as exc: errors[sid] = f"{type(exc).__name__}: {exc}"
    parsed = {}
    for sid in SOURCES:
        try:
            if sid not in raw: raise ValueError(errors.get(sid,"source absent"))
            series = parse_csv(raw[sid], sid)
            receipts[sid]["sha256"] = hashlib.sha256(raw[sid].encode()).hexdigest()
            receipts[sid].update(source_health(series,sid,asof))
            parsed[sid] = series[series.index <= asof]
        except Exception as exc: errors[sid] = str(exc)
    return parsed,receipts,errors,raw,datetime.now(timezone.utc).isoformat()


def read_spec():
    with (REVIEW/"indicators.csv").open(newline="") as f: rows=list(csv.DictReader(f))
    keys=[r["id"] for r in rows]
    if len(keys)!=len(set(keys)): raise ValueError("Duplicate indicator IDs")
    for row in rows:
        if int(row["tier"]) not in (1,2,3): raise ValueError("Indicator tier must be 1, 2 or 3")
        if not set(row["series_ids"].split("|")) <= SOURCES.keys(): raise ValueError("Unknown source in indicator contract")
        if row["threshold_value"]:
            if not np.isfinite(float(row["threshold_value"])): raise ValueError("Threshold must be finite")
            if row["threshold_comparator"] not in ("ge","gt","lt"): raise ValueError("Unknown threshold comparator")
        if row.get("condition_id"):
            if row["condition_id"] not in keys or not row["threshold_value"]: raise ValueError("Invalid compound condition reference")
            if not np.isfinite(float(row["condition_threshold"])): raise ValueError("Condition threshold must be finite")
    return rows


def plain_date(d):
    return str(d.end_time.date()) if isinstance(d,pd.Period) else str(pd.Timestamp(d).date())


def finite_float(value):
    return float(value) if pd.notna(value) and np.isfinite(value) else None


def evaluate(spec, derived, receipts, errors):
    rows=[]
    for item in spec:
        key=item["id"]
        source_ids=item["series_ids"].split("|")
        row={"id":key,"name":item["name"],"tier":int(item["tier"]),"unit":item["unit"],"formula":item["definition"],"threshold_text":item["thresholds"],"action":item["action_it_informs"],"source_url":item["source_url"],"base_rate":item["measured_base_rate"],"false_positive_rate":item["false_positive_rate"],"value":None,"previous":None,"change":None,"distance":None,"history":[],"observation_date":None,"status":"unavailable","error":None}
        issue=[errors[sid] for sid in source_ids if sid in errors]
        if issue: row["error"]="; ".join(issue)
        elif key not in derived: row["error"]="Context series is not automated; manual evidence required"
        else:
            s=derived[key]
            if s.empty or finite_float(s.iloc[-1]) is None:
                row["error"]="Latest derived value unavailable; missing or nonfinite required calendar input"
            else:
                valid=s.dropna()
                value=finite_float(valid.iloc[-1]); row["value"]=value
                row["observation_date"]=plain_date(valid.index[-1])
                row["published_at"]=None
                row["acquired_at"]=max((receipts[sid].get("acquired_at","") for sid in source_ids if sid in receipts),default=None)
                row["sampling_note"]=item.get("sampling_note", "Historical validation uses monthly observations; native-frequency displays are diagnostic only.")
                # Change is one prior observation, not one day for monthly/quarterly series.
                row["previous"]=finite_float(valid.iloc[-2]) if len(valid)>1 else None
                row["change"]=value-row["previous"] if row["previous"] is not None else None
                row["status"]="context" if not item["threshold_value"] else "below"
                if item["threshold_value"]:
                    threshold=float(item["threshold_value"]); comparator=item["threshold_comparator"]
                    if comparator not in ("ge","gt","lt"): raise ValueError(f"Unknown threshold comparator {comparator}")
                    active=(value>=threshold if comparator=="ge" else value>threshold) if comparator!="lt" else value<threshold
                    if item.get("condition_id"):
                        auxiliary=derived.get(item["condition_id"])
                        condition=auxiliary.reindex(s.index).iloc[-1] if auxiliary is not None else np.nan
                        row["condition_value"]=finite_float(condition)
                        row["condition_threshold"]=float(item["condition_threshold"])
                        if finite_float(condition) is None:
                            row["error"]="Compound threshold condition unavailable"
                            row["status"]="unavailable"
                            row["change_unit"]="pp" if row["unit"]=="%" else row["unit"]
                            rows.append(row)
                            continue
                        active=active and condition>=float(item["condition_threshold"])
                    row["distance"]=value-threshold if comparator in ("ge","gt") else threshold-value
                    row["status"]="crossed" if active else "below"
                row["history"]=[{"date":plain_date(d),"value":finite_float(v)} for d,v in s.iloc[-24:].items()]
                row["source_observations"]={sid:receipts[sid] for sid in source_ids if sid in receipts}
        row["change_unit"]="pp" if row["unit"]=="%" else row["unit"]
        rows.append(row)
    return rows


def compare_previous(rows, prior):
    before={r["id"]:r for r in (prior or {}).get("indicators",[])}
    changes=[]
    for row in rows:
        old=before.get(row["id"])
        row["last_run_value"]=old.get("value") if old else None
        row["change_since_last_run"]=(row["value"]-old["value"]) if old and row["value"] is not None and old.get("value") is not None else None
        if old and old.get("status")!=row["status"]:
            changes.append({"id":row["id"],"name":row["name"],"before":old.get("status"),"after":row["status"],"tier":row["tier"]})
    return changes


def report(snapshot):
    lines=[f"# Macro monitoring report — {snapshot['as_of']}","",f"Mode: **{snapshot['mode']}**. Data status: **{snapshot['status']}**. Specification: {VERSION}.","",snapshot["regime"],"", "This is a measurement and review framework. Threshold crossings request investigation; they do not predict prices or specify trades.","", "## What changed",""]
    if snapshot["changes"]:
        lines.extend(f"- {c['name']}: {c['before']} → {c['after']}." for c in snapshot["changes"])
    else: lines.append("No prior comparable reading, or no threshold-state changes. See the value table for measured changes; unchanged is not new evidence.")
    lines += ["","## Readings","","| Indicator | Value | Last observation | State | Δ since prior run |","|---|---:|---|---|---:|"]
    for r in snapshot["indicators"]:
        v="Unavailable" if r["value"] is None else f"{r['value']:.3f} {r['unit']}"
        delta="—" if r["change_since_last_run"] is None else f"{r['change_since_last_run']:+.3f}"
        lines.append(f"| {r['name']} | {v} | {r['observation_date'] or '—'} | {r['status']} | {delta} |")
    lines += ["","## Data exceptions",""]+[f"- {k}: {v}" for k,v in snapshot["errors"].items()]
    if not snapshot["errors"]:lines.append("Required automated sources passed age, schema and derivation checks; source receipt dates remain visible in the dashboard. Snapshot mode is historical, not a fresh source read.")
    lines += ["","## Next review","","Monthly after the main inflation release; weekly automated data-health/fast-state checks. Off-cycle review only for a newly crossed Tier 1 threshold confirmed by the next release, deterioration across distinct labour and credit families, or a source failure. Claims/Sahm and Baa/NFCI overlap; multiple flags are not statistically independent votes. Never use slow valuation context as a timed entry/exit rule.",""]
    return "\n".join(lines)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=["snapshot","live"],default="snapshot")
    parser.add_argument("--as-of",default="2026-09-18")
    parser.add_argument("--output",type=Path,default=REVIEW/"pipeline/output")
    args=parser.parse_args(argv)
    out=safe_path(args.output); out.mkdir(parents=True,exist_ok=True)
    asof=pd.Timestamp(args.as_of).normalize()
    args.as_of=str(asof.date())
    if args.mode=="live":
        if asof.date()!=datetime.now(timezone.utc).date():
            parser.error("Live mode requires --as-of equal to today's UTC date; historical vintages require ALFRED")
    try:
        series,receipts,errors,raw,captured=load_sources(args.mode,asof)
    except (ValueError,OSError) as exc:
        series,receipts,raw={},{},{}
        errors={"source_load":f"{type(exc).__name__}: {exc}"}
        captured=datetime.now(timezone.utc).isoformat()
    try:
        derived=derive(series,asof)
    except ValueError as exc:
        derived={}
        errors["derivation"]=str(exc)
    rows=evaluate(read_spec(),derived,receipts,errors)
    for r in rows:
        if r["error"] and r["tier"]<=2: errors[r["id"]]=r["error"]
    latest=out/"latest.json"
    prior=json.loads(latest.read_text()) if latest.exists() else None
    if prior and (prior["mode"]!=args.mode or prior["spec_version"]!=VERSION or prior["as_of"]>args.as_of): prior=None
    changes=compare_previous(rows,prior)
    active=[r["name"] for r in rows if r["tier"]<=2 and r["status"]=="crossed"]
    regime=("Required data failed validation; regime assessment withheld." if errors else ("Fast-state thresholds crossed: "+", ".join(active)+". Assess each against its false-alarm record." if active else "No monitored fast-state threshold crossed. Structural valuation and profit-share readings remain context; absence of a signal does not establish safety."))
    snapshot={"spec_version":VERSION,"as_of":args.as_of,"mode":args.mode,"generated_at":captured,"status":"failed" if errors else "validated","regime":regime,"indicators":rows,"sources":receipts,"errors":errors,"changes":changes,"cutoff_note":"Supplied raw data captured 2026-09-19, revised history" if args.mode=="snapshot" else "Fresh source reads; history may be revised. No ALFRED vintages."}
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    write_json(REVIEW/"pipeline/attempts"/f"{run_id}.json",snapshot)
    write_json(out/"attempt.json",snapshot)
    if not errors:
        write_json(REVIEW/"pipeline/readings"/f"{run_id}.json",snapshot)
        write_json(latest,snapshot)
        for sid,txt in raw.items():
            target=safe_path(REVIEW/"pipeline/cache"/run_id/f"{sid}.csv");target.parent.mkdir(parents=True,exist_ok=True);target.write_text(txt)
        (out/"report.md").write_text(report(snapshot))
    else:
        (out/"failed_report.md").write_text(report(snapshot))
        print("DATA FAILURE — last validated reading retained; inspect attempt.json",file=sys.stderr)
        for k,v in errors.items():print(f"{k}: {v}",file=sys.stderr)
    print(json.dumps({"status":snapshot["status"],"mode":args.mode,"indicators":len(rows),"errors":len(errors),"attempt":str(out/"attempt.json")}))
    return 2 if errors else 0


if __name__=="__main__":raise SystemExit(main())
