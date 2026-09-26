import React from "react";
import { DataComponent, EvidenceChart, Section, SortableItem, SortableRegion, useDataApp } from "../../data-app-public.jsx";
import "./example.css";

const number = (v, unit="") => v == null ? "Unavailable" : `${Number(v).toLocaleString(undefined,{maximumFractionDigits:2})}${unit ? ` ${unit}` : ""}`;
const signed = (v,unit="") => v == null ? "No prior reading" : `${v>0?"+":""}${number(v,unit)}`;
const state = { below:"Not crossed", crossed:"Review threshold crossed", context:"Context only", unavailable:"Unavailable" };
const humanEvidence = (s="") => s.replaceAll("recession_present_or_onset","recession already present or beginning within the horizon").replaceAll("recession_onset","a new recession").replaceAll("equity_entry_loss_20","a 20% equity price loss from the signal-month level").replaceAll("inflation_cross_4","inflation crossing 4%").replaceAll("credit_cross_3","the Baa spread crossing 3 percentage points");

export function DashboardContent(){
  const {snapshot,reviewedRows,visible} = useDataApp();
  const monitor=snapshot.monitor;
  const all=monitor.indicators;
  const [selected,setSelected]=React.useState("claims_rise");
  const [tier,setTier]=React.useState("all");
  const inspect=(id)=>{setSelected(id);document.getElementById("evidence-heading")?.scrollIntoView({behavior:"smooth",block:"start"});};
  const chosen=all.find(r=>r.id===selected)||all[0];
  const history=reviewedRows(`history_${chosen.id}`);
  const filtered=all.filter(r=>tier==="all"||r.tier===Number(tier));
  return <article className="macro-page">
    <DataComponent id="regime-state" queryId="monitor_status" title="Current reading" kind="metrics" variant="plain" displayRows={reviewedRows("monitor_status")}>
      <div className={`macro-state ${monitor.status==="failed"?"macro-failed":""}`} data-reviewed-rows>
        <p className="macro-dateline">As of {monitor.as_of} · {monitor.mode==="snapshot"?"Historical snapshot":"Source refresh"} · {monitor.status==="failed"?"Data failure":"Sources checked"}</p>
        <p className="macro-lead">{monitor.regime}</p>
        <p className="macro-muted">{monitor.changes.length ? `${monitor.changes.length} threshold-state changes since the prior comparable run.` : "No threshold-state change recorded. Initial readings have no prior-run comparison."} {monitor.cutoff_note}</p>
      </div>
    </DataComponent>
    <Section id="tier-one-heading" title="Tier 1 · review when crossed" spacing="content">
      <p className="macro-muted">Three diagnostic flags. A crossing requests investigation; it is not a price forecast or a trade instruction.</p>
      <SortableRegion id="macro:diagnostics" variant="canvas" spacing="standard" columns={12} rows={[{id:"diagnostic-cards",kind:"metrics",items:all.filter(r=>r.tier===1).map(r=>`signal-${r.id}`)}]}>
        {all.filter(r=>r.tier===1).map(r=><SortableItem key={r.id} id={`signal-${r.id}`} label={r.name} kind="metric" span={4}>
          <DataComponent id={`signal-${r.id}`} queryId={r.id} kind="metrics" title={r.name} variant="card" displayRows={[r]}>
            <div data-reviewed-rows>
              <div className="macro-value">{number(r.value,r.unit)}</div>
              <p className={`macro-badge macro-${r.status}`}>{state[r.status]}</p>
              <p>Threshold {r.threshold_text}</p>
              <p className="macro-muted">{r.distance==null?"":`${number(Math.abs(r.distance),r.change_unit)} ${r.distance>=0?"past":"short of"} threshold · `}{r.observation_date||"No observation"}</p>
              <p className="macro-muted">Latest observation change: {signed(r.change,r.change_unit)}</p>
              <button className="macro-text-button" onClick={()=>inspect(r.id)} aria-label={`Inspect ${r.name}`}>Inspect history and false alarms ↓</button>
              {r.error&&<p className="macro-error">{r.error}</p>}
            </div>
          </DataComponent>
        </SortableItem>)}
      </SortableRegion>
    </Section>
    <Section id="all-readings-heading" title="Watch and context" spacing="after-metrics">
      <label className="macro-control">Show <select value={tier} onChange={e=>setTier(e.target.value)} aria-label="Indicator tier"><option value="all">All 12 indicators</option><option value="1">Tier 1 · review</option><option value="2">Tier 2 · watch</option><option value="3">Tier 3 · context</option></select></label>
      <div className="macro-table-wrap">
        <table className="macro-table"><thead><tr><th>Indicator</th><th>Value</th><th>Threshold</th><th>Distance</th><th>Direction</th><th>Observation</th><th>State</th></tr></thead>
        <tbody>{filtered.map(r=><tr key={r.id} data-reviewed-rows><th><button onClick={()=>inspect(r.id)} className="macro-text-button">{r.name}</button><small>Tier {r.tier}</small></th><td>{number(r.value,r.unit)}</td><td>{r.threshold_text}</td><td>{r.distance==null?"—":signed(r.distance,r.change_unit)}</td><td>{r.change==null?"—":`${r.change>0?"↑":r.change<0?"↓":"→"} ${number(Math.abs(r.change),r.change_unit)}`}</td><td>{r.observation_date||"—"}</td><td>{state[r.status]}</td></tr>)}</tbody></table>
      </div>
      <p className="macro-muted">Distance is signed toward crossing; positive means beyond the numeric boundary. Inflation acceleration also requires headline inflation ≥4%. Direction compares consecutive source observations, which have different cadences.</p>
    </Section>
    <Section id="evidence-heading" title="Indicator evidence" spacing="content">
      <label className="macro-control">Inspect <select value={selected} onChange={e=>setSelected(e.target.value)} aria-label="Inspect indicator">{all.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <div className="macro-evidence">
        {visible(`history-${chosen.id}`)&&<EvidenceChart key={chosen.id} id={`history-${chosen.id}`} queryId={`history_${chosen.id}`} title={`${chosen.name} · ${chosen.unit}`} variant="card" rows={history} sourceRows={history} height={230} spec={{type:"line",x:"date",y:"value",valueDecimals:2,startAtZero:false,showLegend:false,showXAxisLabel:false,showYAxisLabel:false,stackable:false}} />}
        <DataComponent id={`evidence-${chosen.id}`} queryId={chosen.id} title="What the flag has meant" kind="table" variant="card" displayRows={[chosen]}>
          <div data-reviewed-rows className="macro-evidence-text"><p><strong>Use</strong> {chosen.action}</p><details open><summary>Measured base rate</summary><p>{humanEvidence(chosen.base_rate)}</p></details><details><summary>False alarms and uncertainty</summary><p>{chosen.false_positive_rate}</p></details><details><summary>Definition and source dates</summary><p>{chosen.formula}</p>{Object.entries(chosen.source_observations||{}).map(([sid,s])=><p key={sid}><a href={`https://fred.stlouisfed.org/series/${sid}`} target="_blank" rel="noreferrer">{sid}</a> · observation {s.observation_date} · period ends {s.period_end} · next observation due by {s.next_observation_due_by}.<br/>{s.freshness_basis} · Acquired {s.acquired_at||"in supplied capture"}; exact publication time unknown.</p>)}</details>{chosen.error&&<p className="macro-error">{chosen.error}</p>}</div>
        </DataComponent>
      </div>
      <p className="macro-muted">Chart shows the last 24 native observations; calendar spacing and missing values are retained. Full tests, alarm dates, assumptions and source receipts are included in the review package.</p>
    </Section>
  </article>;
}
