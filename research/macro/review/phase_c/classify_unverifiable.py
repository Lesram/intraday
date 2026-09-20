"""Manual second-reader taxonomy of a preselected 48-row unverifiable sample.
Categories describe why a claim cannot be settled here; they are not new truth labels.
"""
from pathlib import Path
import csv,collections,json
OUT=Path(__file__).resolve().parent
decisions=[
('vague_inference','No horizon or operational definition for pressure toward printing; yield observations themselves testable.'),
('normative_rhetorical','Advice and sales reassurance; no measurable universal skill criterion.'),
('private_performance','Requires named security, dated entry/exit and full portfolio record.'),
('public_evidence_missing','Named interpreter and exact dates: daily yields can test levels; original citation and intraday timing still needed.'),
('public_evidence_missing','Apollo/Athene filings can in principle resolve asset amount and affiliation; not unfalsifiable.'),
('underspecified_measure','Which homebuilders, index, starting date and return convention? Sixfold is testable once specified.'),
('public_evidence_missing','Identify dated New York Fed SOMA projection and scenario; not inherently unknowable.'),
('private_performance','Undisclosed strategy exposures and retrospective claims require a dated journal.'),
('normative_rhetorical','Universal worst-action assertion without utility or horizon.'),
('vague_inference','Conditional funding warning lacks magnitude and deadline; cannot count as settled forecast.'),
('private_performance','Personal debt/property transactions not in supplied public evidence.'),
('underspecified_measure','207 tonnes lacks demand category, period and consistent historical universe.'),
('private_performance','Cash-attractiveness formula and chart inputs withheld.'),
('private_performance','Needs audited dated equity curve, fees, exposure and benchmark.'),
('private_performance','Needs complete trade list including losses and overlapping positions.'),
('normative_rhetorical','Preparedness advice without an outcome or deadline.'),
('commercial_service','Historical advertised price and actual sale price are testable with archived terms.'),
('vague_inference','Public quote can be checked, but assertion about private understanding is mind-reading.'),
('public_evidence_missing','Compound row: TIC flows, World Bank requests and yield changes can be checked separately.'),
('private_performance','Repeated successful timing lacks a complete predated journal.'),
('public_evidence_missing','Accounting cashflow statement and defined capex series can test historical low; clip attribution also needed.'),
('normative_rhetorical','Unqualified profit/wipeout claim is sales rhetoric.'),
('commercial_service','Four videos/month and lifetime access are service terms; prior note about timing claims is mismatched.'),
('public_evidence_missing','Archived GDPNow component vintages can test change; later nominal retail sales cannot refute earlier forecast.'),
('commercial_service','Price, discount and caption require audio and dated offer page; do not assume caption repair proven.'),
('public_evidence_missing','Conference Board stock expectations distinct from Michigan general sentiment; obtain exact question history.'),
('public_evidence_missing','UK2y yield history and window can test largest move; missing local series is not unknowability.'),
('commercial_service','Membership timing/service promise could be audited with authorized access.'),
('public_evidence_missing','Statistical birth/participation hypothesis can be tested after fixing transform and error metric; economics alone cannot reject fit.'),
('underspecified_measure','Company universe and cashflow sensitivity model absent.'),
('commercial_service','Mixed personal history and dated sponsor terms: verify individual public clauses separately.'),
('public_evidence_missing','Named pollster and numerical result are externally falsifiable.'),
('commercial_service','Premium publication/access promise is verifiable in principle; private investment details are separate.'),
('vague_inference','Extreme/unsustainable undefined and no deadline; includes evaluation rather than datapoint.'),
('public_evidence_missing','Public clips and quotation attribution can be checked if source/date located.'),
('public_evidence_missing','Post/account existence and views are testable; claimed oracle record requires complete archived sequence.'),
('underspecified_measure','Wide range is not inherently unfalsifiable; missing counterfactual, expenditure definition and horizon are the issue.'),
('normative_rhetorical','Introduction/advice, not a scored prediction.'),
('private_performance','Comparative highest-performing proprietary strategy lacks consistent disclosed results.'),
('public_evidence_missing','Embedded next-few-weeks index-inclusion prediction is dated and checkable despite recommendation type.'),
('commercial_service','Archived pricing/audio could resolve offer; institutional price not established.'),
('underspecified_measure','Cash numerator unspecified; equity denominator versus GDP denominator need not contradict.'),
('commercial_service','App features/free booking externally checkable; recommendation itself has no truth score.'),
('normative_rhetorical','Advice and value judgment.'),
('private_performance','Self-reported holdings need voluntary disclosures; not evidence of falsehood.'),
('underspecified_measure','Market, platform and liquidation definition absent; account count might be externally traceable.'),
('vague_inference','Hidden storage plus an unbounded may-hold-more claim excludes observable resolution.'),
('normative_rhetorical','Advice about responding to volatility lacks a testable portfolio and horizon.'),
]
rows=list(csv.DictReader((OUT/'unverifiable_sample.csv').open()));assert len(rows)==len(decisions)==48
for r,(cat,reason) in zip(rows,decisions):r.update(review_category=cat,review_reason=reason)
with (OUT/'unverifiable_review.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
result={'n':48,'categories':dict(collections.Counter(x[0] for x in decisions)),'warning':'One primary category per compound row; manual taxonomy, not independent truth verification. Original notes were visible for this taxonomy; distinct from72-row blind verdict experiment.'}
(OUT/'unverifiable_review_summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
