"""Post-seal comparison. Never changes the sealed blind judgments."""
from pathlib import Path
import collections,csv,datetime,hashlib,json

P=Path(__file__).resolve().parent
seal=json.loads((P/'second_reader_blind_seal.json').read_text())
assert all(hashlib.sha256((P/k).read_bytes()).hexdigest()==v for k,v in seal['files'].items())
old={r['claim_id']:r for r in csv.DictReader((P/'original_labels_DO_NOT_OPEN_BEFORE_JUDGING.csv').open())}
new=list(csv.DictReader((P/'second_reader_blind.csv').open()))
design=json.loads((P/'blind_sampling_design.json').read_text())
N={r['input_package']:r['eligible'] for r in design['packages']}
n={r['input_package']:r['sampled'] for r in design['packages']}
W={k:N[k]/n[k] for k in N}
def group(v):
    return 'supported' if v in {'TRUE','MOSTLY_TRUE','TRENDING'} else 'adverse' if v in {'FALSE','MISLEADING'} else 'unresolved'
def write(name,rows):
    with (P/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),quoting=csv.QUOTE_ALL);w.writeheader();w.writerows(rows)

# Explicit post-unblinding interpretation of disagreements, not retroactive
# amendments of the independent labels. Number keys refer to blind CSV order.
T={
1:('same_evidence_severity','Both notes recognize FTSE true/S&P headline-index claim wrong. Disagreement is how material the S&P scope error is; not a newly discovered factual difference.'),
2:('new_public_evidence','Old pass lacked single-stock prices; second reader found dated public price tables. Source-availability improvement, not proof the old UNVERIFIABLE was improper.'),
3:('same_evidence_severity','Both distinguish realized revenue from annualized run rate. Old pass identifies 2024 endpoint as run rate too, so the blind suggestion of mismatched 2024 annual revenue is not independently settled. Material-label threshold remains disputed.'),
4:('operationalization_difference','Old pass identifies a Ken French proxy and distinguishes utilities from manufacturing; blind reader required specified sector/index onset and did not reproduce that proxy. Do not call old MISLEADING wrong merely because the blind label is UNVERIFIABLE.'),
5:('temporal_and_metric_evidence_defect','Original TRUE note relies on September 6 material after the June 29 video and 2027 capex/cloud-revenue evidence for a 2026 capex/operating-cash-flow claim. This evidentiary mismatch is demonstrable even though earlier research supports the approximate claim.'),
7:('same_evidence_severity','Both document controlled scheming and reject proof of an innate survival instinct. Difference is whether the overreach deserves MISLEADING rather than MOSTLY_TRUE.'),
10:('source_convention_difference','Old pass uses its own spliced earnings-yield series; blind reader found raw Shiller earnings stale. Need audit splice and availability before resolving. Blind UNVERIFIABLE is not a refutation of the original measured spread.'),
11:('missed_embedded_attribution','Original generic advice label misses a factual claim that published headlines existed in July 2025. Dated Apollo/press examples make that component checkable.'),
14:('unsupported_primary_precision','Original acknowledges no primary re-derivation and gives a different starting weight; blind reader withholds support without a matching series. Not a proven incorrect historical direction.'),
18:('context_and_precision','Both accept the 30-year auction record; blind reader qualifies the broader phrase. Same collapsed class, not a substantive reversal.'),
19:('added_condition','Old note emphasizes first intervention in 2010; claim says stepped in in 2011, not first. Second reader avoids inserting first. Both support central event.'),
21:('checked_fragment_not_mechanism','Original verifies relief dates and labels whole row TRUE but does not test smooth/choppy causal attribution or bank-purchase magnitude. Blind adverse label concerns that untested mechanism, not the genuine regulation.'),
27:('new_public_evidence_and_scope','New primary METI and contemporaneous reporting corroborate country developments and contradict Russia-only implication. Old UNVERIFIABLE reflects missing sources.'),
28:('benchmark_definition','Original accepts broad normal $20-40 to about $100; blind reader requires matching benchmark/start. There is positive independent evidence of much wider cracks; this disagreement does not prove original direction false.'),
29:('asof_and_counterfactual_evidence','Original April 20 note invokes offsets by May, Q2 demand/import changes and June 30 price to say a future shortage did not occur. That is lookahead for an as-of fact check and mixes forecast resolution with capacity arithmetic. Blind reader leaves the exact capacity sum unresolved.'),
30:('new_public_evidence','Treasury August 24 announcement and direct press clips were located in blind review. Old UNVERIFIABLE is a source-search miss, not necessarily an interpretive bias.'),
31:('precision_and_geographic_scope','Both support broad manufacturing shares; blind reader does not independently reproduce exact Eurozone 15% and distinguishes EU/Eurozone. No demonstrated contradiction.'),
32:('rounding_and_recording_cutoff','Both calculations show about 40% WTI rise. Difference is normal rounding and use of prior close versus video-day close.'),
33:('wrong_underlying_fact_mapping','Original fact_key/note validate Gromen gold-import/surplus and Hamiltonian attribution dated July 15. Sample claim is May 4 OPEC necessity under gold-backed money. They are different propositions; source attribution was propagated too broadly.'),
35:('policy_date_threshold','Both identify January 1934 versus 1933. Original calls it a minor detail; blind reader follows exact policy-date convention. This is severity, not disputed chronology.'),
36:('plan_vs_execution_precision','Both describe a three-year plan, not completed capacity. Same supported group; the wording currently expanding is compatible with a program already underway.'),
37:('trend_vs_completed_label','Same measured yuan appreciation, TRUE versus TRENDING. Original uses later September values, but pre-video values already suffice; no change to supported class.'),
39:('universal_vs_aggregate_scope','Both reject broad disappearance of Treasury demand. Blind reader tests all central banks stopped buying, while original emphasizes roughly flat aggregate official holdings. FALSE/MISLEADING boundary rather than support reversal.'),
40:('same_evidence_severity','Both know this was a proposal and distinguish it from executed sales. Whether announced a cut implies execution is interpretive; do not count this as independently proven original error.'),
43:('possibility_vs_implication','Original correctly treats token controls as technically possible but not statutory requirements. Blind label is harsher about implied compulsory design; claim uses can, so this adverse judgment is debatable. Do not retroactively erase it or present it as proven error.'),
46:('checked_fragment_not_mechanism','Original verifies NSFR factor/date but does not substantiate no longer operating an unallocated shell game at scale. The claim bundles genuine regulation with a stronger market-mechanism conclusion.'),
48:('minor_context_threshold','Both confirm proposed 55%-to-20% change; blind reader qualifies repatriation motive. Same supported class.'),
49:('cash_definition_and_embedded_fact','Original labels advice UNVERIFIABLE and interprets cash as remunerated Treasury bills. Blind reader scores nominal non-interest cash identity, with an explicit bill-yield caveat. Resolving cash definition matters more than declaring either reader wrong.'),
50:('same_evidence_severity','Both find October 2007 top, three months after July, and roughly 57% daily decline. Difference is materiality of six-month lead claim.'),
52:('population_definition','Same approximate count and population; blind reader qualifies shareholder versus active trader count. Same supported group.'),
53:('new_primary_contradiction','Original substitutes crude prices and generic pass-through for the claimed pump price, even citing end-March outcomes after March 20. AAA March 19 national pump data gives approximately +33%, materially below +50%. Strong specific correction.'),
54:('lookahead_evidence_but_direction_supported','Original June 18 claim evidence extends to August. That as-of error is demonstrable, but pre-video CPI already supports a post-2021 acceleration. Label downgrade is caution over pace/level wording, not denial of inflation.'),
55:('lookahead_evidence_but_direction_supported','Original April 8 evidence includes Q1/Q2 2026 GDP unavailable that day. Prior years already support approximate 2-3% YoY growth. Fix calendar without treating directional proposition as false.'),
56:('wrong_underlying_fact_mapping','Same original fact_key and identical note were propagated to general 14M population and distinct two-stock leveraged-causation claim. Population count does not verify how many held those stocks or drove their rally.'),
57:('historical_offer_scope','Original generic current CookUnity 50% offer does not establish historical Andre-code eligibility. Blind reader stricter on exact offer; not proof promotion was false.'),
63:('same_evidence_severity','Both confirm partnerships but cannot source the universal requirement attribution. Difference is materiality of unsupported universal-compulsion framing.'),
64:('same_evidence_severity','Both find an election reset and no source for martial law. Blind reader matched November bus exercise. Severity disagreement; source silence does not prove no participant used those words.'),
67:('wrong_underlying_fact_mapping','Sample claim is 468% five-year performance only; original MISLEADING verdict is based on a separate 8x-S&P comparison from another timestamp/video. Original note itself calls the actual strategy return unverifiable. Split the atoms.'),
68:('public_subfact_private_performance','Original confirms MU stock return but concedes holding continuity is paywalled/self-reported. That subfact does not independently confirm sponsor trading behavior or rationale.')
}

pairs=[]
for i,r in enumerate(new,1):
    o=old[r['claim_id']];a,b=group(o['verdict']),group(r['verdict'])
    disagree=o['verdict']!=r['verdict']
    assert disagree == (i in T), (i,r['claim_id'])
    typ,assessment=T.get(i,('same_label','Exact labels agree; this does not imply identical sources, denominator definitions or proof of the whole causal narrative.'))
    pairs.append(dict(claim_id=r['claim_id'],input_package=r['input_package'],old_verdict=o['verdict'],blind_verdict=r['verdict'],
       old_group=a,blind_group=b,exact_disagreement=int(disagree),collapsed_disagreement=int(a!=b),
       old_eligible=int(a!='unresolved'),blind_eligible=int(b!='unresolved'),eligibility_change=int(a=='unresolved')-int(b=='unresolved'),
       sampling_weight=W[r['input_package']],comparison_type=typ,post_unblinding_assessment=assessment,
       old_source=o['source'],old_note=o['note'],blind_source=r['source'],blind_note=r['note']))
write('second_reader_comparison.csv',pairs)
packages=[];confusions=[]
for pkg in N:
    rs=[r for r in pairs if r['input_package']==pkg]
    packages.append(dict(input_package=pkg,population_covered_claims=N[pkg],sample_n=len(rs),weight=W[pkg],
       exact_disagreements=sum(r['exact_disagreement'] for r in rs),collapsed_disagreements=sum(r['collapsed_disagreement'] for r in rs),
       old_eligible=sum(r['old_eligible'] for r in rs),blind_eligible=sum(r['blind_eligible'] for r in rs),
       old_supported=sum(r['old_group']=='supported' for r in rs),blind_supported=sum(r['blind_group']=='supported' for r in rs),
       old_adverse=sum(r['old_group']=='adverse' for r in rs),blind_adverse=sum(r['blind_group']=='adverse' for r in rs)))
    for level,acol,bcol in [('exact','old_verdict','blind_verdict'),('collapsed','old_group','blind_group')]:
        cnt=collections.Counter((r[acol],r[bcol]) for r in rs)
        for (aa,bb),ct in sorted(cnt.items()):confusions.append(dict(input_package=pkg,level=level,old=aa,blind=bb,n=ct,weighted_claims=ct*W[pkg]))
write('second_reader_package_comparison.csv',packages)
write('second_reader_package_confusion.csv',confusions)
def summary(rs,weighted=False):
    def weight(r):return r['sampling_weight'] if weighted else 1
    size=sum(weight(r) for r in rs)
    result={'total':size}
    for side in ['old','blind']:
        cnt=collections.Counter()
        for r in rs:cnt[r[side+'_group']]+=weight(r)
        result[side]=dict(cnt)
        result[side]['resolved']=cnt['supported']+cnt['adverse']
        result[side]['supported_among_resolved']=cnt['supported']/(cnt['supported']+cnt['adverse'])
    for k in ['exact_disagreement','collapsed_disagreement']:
        result[k+'_count']=sum(weight(r)*r[k] for r in rs)
        result[k+'_fraction']=result[k+'_count']/size
    result['became_eligible']=sum(weight(r) for r in rs if r['eligibility_change']==1)
    result['became_unresolved']=sum(weight(r) for r in rs if r['eligibility_change']==-1)
    result['collapsed_confusion']={a+' -> '+b:sum(weight(r) for r in rs if r['old_group']==a and r['blind_group']==b) for a in ['supported','adverse','unresolved'] for b in ['supported','adverse','unresolved']}
    return result

result={'compared_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'blind_seal_valid':True,
 'blind_sealed_at_utc':seal['sealed_at_utc'],'sampling_design':design,
 'unweighted':summary(pairs),'package_population_weighted':summary(pairs,True),
 'cautions':['Disagreement is not an error rate for the original analyst or a truth probability.',
 'Weight N_h/n_h expands covered claim-row strata; equal package sampling is not prevalence proportional.',
 'Stable hash ranking acts as pseudo-random selection, but no formal randomization or cluster-independent sampling claim is made.',
 'Underlying facts repeat across rows and packages; effective independent sample size is below 72.',
 'Resolved-label denominators change with source access, claim scope and interpretation.',
 'Do not subtract this sample rate change from the published 82.1% or replace it with the weighted blind ratio.',
 'Blind ratings are frozen even when post-unblinding evidence raises legitimate doubts; such differences are documented separately.']}
(P/'second_reader_comparison_summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['unweighted','package_population_weighted']},indent=2))
