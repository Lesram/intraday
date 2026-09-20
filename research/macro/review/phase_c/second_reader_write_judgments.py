"""Serialize 72 individually researched, manually adjudicated blind judgments.

This is not a verdict classifier. Every J() call below is a human-readable
judgment made before opening the original labels. Do not rerun after sealing.
"""
from pathlib import Path
import csv, collections, hashlib, json

HERE = Path(__file__).resolve().parent
claims = list(csv.DictReader((HERE / 'blind_claims.csv').open()))
assert len(claims) == 72
R = []
def J(i, verdict, fact_key, measured, source, reason, uncertainty='low', scope='factual'):
    c = claims[i-1]
    R.append(dict(claim_id=c['claim_id'], fact_key=fact_key, verdict=verdict,
        measured_value=measured, as_of_date=c['video_date'], source=source,
        note=reason, uncertainty=uncertainty, adjudication_scope=scope,
        accuracy_denominator_eligible=int(verdict not in ('UNVERIFIABLE','OPEN')),
        channel=c['channel'], input_package=c['input_package'], timestamp=c['timestamp']))

RAW = 'review/phase_c/second_reader_data_checks.json; data/raw/; scripts/factbase.py'
CORPUS = 'corpus/transcripts/'

J(1,'MISLEADING','index_ipo_fast_entry_june2026',
 'FTSE Russell announced conditional fifth-trading-day entry May 26; S&P June 4 consultation retained 12-month IPO seasoning and profitability rules.',
 'https://www.lseg.com/en/media-centre/press-releases/ftse-russell/2026/ftse-russell-introduces-ipo-fast-entry-enhancements-for-russell-us-indexes; https://press.spglobal.com/2026-06-04-S-P-Dow-Jones-Indices-Consultation-on-Treatment-of-MegaCap-Companies-Results',
 'The FTSE component is real, but S&P was explicitly not doing the same as of the preceding day. Universal coordination and suspicious timing are not established by the policy documents.')
J(2,'MOSTLY_TRUE','three_megacap_drawdowns_june2026',
 'June 26 closes AAPL 283.78 and AMZN 232.69; observed prior intraday highs 317.40 and 278.56 imply -10.6% and -16.5%. NVDA June 26 192.53 versus June 2 high 232.01 implies -17.0%.',
 'https://www.financecharts.com/compare/AAPL,AMZN,NVDA/summary/price; https://www.statmuse.com/money/ask/nvda-june',
 'The recent drawdowns have the stated direction and approximate scale, but 12/17/18 are not an exact common closing-price calculation. Recording time, intraday versus closing highs and dividend adjustments are unspecified. These are public data publishers, not exchange-certified extracts.', 'medium')
J(3,'MISLEADING','anthropic_arr_74b',
 'Company May 28 disclosure: annualized run rate above $47B; TickerTrends July estimate about $74B ARR, repeated by ARK/Tema. Neither is $74B realized annual revenue.',
 'https://www.anthropic.com/news/series-h; https://www.ark-invest.com/newsletters/issue-521; https://temaetfs.com/insights/anthropic-the-economics-of-an-ai-pioneer?hs_amp=true; https://www.linkedin.com/in/adriennav',
 'Large growth is real, but an external high-frequency run-rate estimate is presented as company revenue and compared to a 2024 annual amount without matching periods or accounting scope. The 70x calculation cannot establish like-for-like realized revenue growth.', 'medium')
J(4,'UNVERIFIABLE','1929_sector_six_month_lead',
 'Shiller monthly-average broad-market decline September 1929 to June 1932 is about 84.8%; the sector indices, relative-return baseline and signal date are not identified.',
 RAW+'; corpus/transcripts/bravos_2026-09-16_jx3Ll-GJtMY.txt @4:46',
 'The crash magnitude is broadly supportable. Exactly six months of predictive lead from utilities AND industrials cannot be reproduced without the underlying sector series and a pre-specified onset rule. Historical analogy is not established by confirming the subsequent crash.', 'high','mixed_historical_analogy')
J(5,'MOSTLY_TRUE','hyperscaler_capex_ocf_projection_2026',
 'March 19 Columbia research Figure 1 projects five hyperscalers capex approaching operating cash flow in 2026; contemporary estimates span roughly 90-100%.',
 'https://business.columbia.edu/sites/default/files-efs/imce-uploads/svannieuwerburgh/papers/FinancingAIBuildout_03192026.pdf; https://am.gs.com/cms-assets/gsam-app/documents/insights/en/2026/market_monitor_050826.pdf',
 'Supported as an estimate known before the video, not an observed full-year outcome. Total hyperscaler capital expenditure is broader than exclusively AI spending and cash flow must mean operating cash flow, not free cash flow.', 'medium')
J(6,'TRUE','musk_ai_nuclear_quote',
 'Musk made the AI-versus-nuclear-warheads comparison at SXSW in March 2018.',
 'https://schedule.sxsw.com/2018/events/PP100208; https://globalnews.ca/video/4076983/elon-musk-calls-lack-of-a-i-oversight-insane-says-its-more-dangerous-than-nukes/',
 'Quote attribution checks out. TRUE applies to what Musk said; relative AI/nuclear danger is an opinion, not a measured probability validated by this quotation.', 'low','attribution_only')
J(7,'MISLEADING','controlled_model_self_copy',
 'Apollo Research describes controlled December 2024 evaluations involving shutdown avoidance, attempted exfiltration/self-copy and denial; prompts and opportunities were deliberately constructed.',
 'https://apolloresearch.ai/science/demo-example-scheming-reasoning-evaluations',
 'The laboratory behaviors are documented and the video does acknowledge a controlled lab. A general or innate survival instinct being proven goes beyond the result, especially without reporting prompting conditions and low-frequency complete sequences.')
J(8,'MOSTLY_TRUE','hyperscaler_lease_commitments_aug2026',
 'Myrmikan August 14 cites Goldman estimates of approximately $1.5T commitments, including about $1T for leases not yet commenced.',
 'https://www.myrmikan.com/pub/Myrmikan_Research_2026_08_14.pdf pp.11-12; https://www.edwardconard.com/macro-roundup/the-hyperscalers-exploding-purchase-commitments-reach-1-5tn/',
 'The published estimate and order of magnitude match. Not appearing as a recognized balance-sheet lease liability does not mean no disclosure: uncommenced commitments can be disclosed in notes. Goldman underlying workbook was not independently accessible.', 'medium')
J(9,'MOSTLY_TRUE','sp500_july2025_may2026_gain',
 'SP500 May 28 2026 7563.63; gain from any July 2025 close ranges 18.37%-22.03%; May 29 close 7580.06 changes the range only slightly.',
 RAW+'; FRED SP500',
 'Another substantial rally is supported, but 25% overstates the gain from the specified month by at least about three percentage points. It is not an exact TRUE result under the protocol rounding test; broad direction and rough magnitude justify MOSTLY_TRUE.', 'medium')
J(10,'UNVERIFIABLE','cash_vs_stocks_earnings_yield_extreme',
 'Raw Shiller earnings end June 2023 despite later price observations; no reproducible August 2026 numerator or contemporaneous chart series was supplied.',
 RAW+'; corpus/transcripts/bravos_2026-08-09_rv4PIOsQq_g.txt @3:00-4:39',
 'Trailing versus forward earnings, equity universe and chart transformation matter. A current-price/old-earnings calculation would be invalid. I cannot verify the claimed rank against 1990, 2000 and 2007 using the available complete observations.', 'high')
J(11,'MOSTLY_TRUE','media_bubble_headlines_july2025',
 'Apollo July 16 2025 published a comparison with the 1990s IT bubble; Axios July 22 ran a 1999-like bubble/2000s-crash headline.',
 'https://www.apolloacademy.com/ai-bubble-today-is-bigger-than-the-it-bubble-in-the-1990s/; https://www.axios.com/2025/07/22/stock-market-bubble-wall-street',
 'Existence and July timing of prominent bubble coverage are supported. This does not establish that all mainstream media shared a view, and the exact unspecified 2007 comparison was not identified.', 'medium','attribution_and_scope')
J(12,'UNVERIFIABLE','passive_stops_working_recommendation',
 'No defined conditions, investment horizon, return benchmark or failure criterion accompanies the advice.',
 CORPUS+'bravos_2026-09-12_RUH3BPQ5fTo.txt @18:42',
 'Advice and a conditional market thesis, not a resolved factual observation. Claims that timing will not work or passive investing stops working cannot receive a factual accuracy mark without operational definitions.', 'high','nonfactual_recommendation')
J(13,'TRUE','peter_lynch_correction_quote',
 'The correction-preparation maxim is consistently attributed to Peter Lynch in publisher and investment-industry records predating the video.',
 'https://catalogimages.wiley.com/images/db/pdf/9781118929001.excerpt.pdf; https://www.hartfordfunds.com/dam/en/docs/pub/prospectingmaterials/Brochures/P3320.pdf',
 'Accept the attribution, not a universally quantified empirical loss comparison. The original Worth interview was not retrieved, so confidence is lower than a direct recording.', 'medium','attribution_only')
J(14,'UNVERIFIABLE','tech_earnings_and_weight_1995_2000',
 'FRBSF June 2001 confirms very fast tech earnings growth, but its constant-company sample differs from S&P sector aggregate earnings and cannot verify the stated 2x and 15%-30% pair.',
 'https://www.frbsf.org/research-and-insights/publications/economic-letter/2001/06/the-stock-market-what-a-difference-a-year-makes/; https://archive.yardeni.com/pub/t_051128.pdf',
 'Sector classification, earnings convention, start/end month and point-in-time constituents are absent. The two exact historical comparisons remain unverified; this is not evidence that they are false.', 'high')
J(15,'UNVERIFIABLE','sit_out_investment_boom_advice',
 'Normative advice with no investor circumstances, horizon or measurable worst-case criterion.',
 CORPUS+'bravos_2026-09-16_jx3Ll-GJtMY.txt @18:16',
 'Not a fact-checkable statement as phrased. A rhetorical investment recommendation should not count as either a confirmed fact or a forecast hit.', 'high','nonfactual_recommendation')
J(16,'UNVERIFIABLE','ninety_percent_sell_bottom',
 'No public study or defined investor denominator supports 90% selling at the bottom.',
 CORPUS+'bravos_2026-05-01_YUwjueXzffE.txt @7:38',
 'The embedded percentage is testable in principle but no population, period or definition of bottom is provided. General evidence of poor investor timing cannot verify 90%; the surrounding advice is nonfactual.', 'high','recommendation_embedded_number')
J(17,'TRUE','treasury_30y_auction_aug2026',
 'August 13 2026 30-year auction high yield 5.216%; August 2001 auction 5.52% is the previous higher long-bond sale cited in contemporaneous records.',
 'https://www.treasurydirect.gov/instit/annceresult/press/preanre/2026/R_20260813_3.pdf; https://www.publicnow.com/view/2B2E7732D93C6B6EF1FFCACF88AFFAC62F1583B9; https://squawkdeck.com/sources/us-treasury-auctions/reports/2026-08-13-30-year',
 'Valid auction comparison, not a claim that daily secondary-market yields never exceeded this level after 2001. Direct Treasury PDF retrieval failed; CME issuer commentary and dated result mirrors corroborate the sale.', 'medium')
J(18,'MOSTLY_TRUE','long_borrowing_25year_high_context',
 'Preceding transcript specifies the 30-year auction. That sale is a roughly 25-year auction high; DGS30 5.24% on September 4 had been matched as recently as July 2007.',
 RAW+'; corpus/transcripts/bravos_2026-09-05__rwFYNlKtEc.txt @0:23-0:55; https://squawkdeck.com/sources/us-treasury-auctions/reports/2026-08-13-30-year',
 'Read with the immediately preceding auction context, the central assertion is supported. As a stand-alone statement about every long-term borrowing yield it is too broad. Do not refute an auction record with a different constant-maturity series.', 'medium')
J(19,'TRUE','ecb_greece_intervention_2011',
 'ECB Securities Markets Programme began May 10 2010 and continued in 2011; July 2011 ECB remarks address the Greek rescue.',
 'https://www.ecb.europa.eu/mopo/implement/app/html/index.pl.html; https://www.ecb.europa.eu/press/key/date/2011/html/sp110722.et.html',
 'The statement says intervened in 2011, not first intervened in 2011. Ongoing 2011 intervention is true; silently adding first would create a spurious error.')
J(20,'MOSTLY_TRUE','cayman_funds_37pct_net_issuance',
 'Fed October 15 2025 paper estimates Cayman hedge funds acquired $1.2T January 2022-December 2024, approximately 37% of net coupon issuance assuming purchases were all notes/bonds.',
 'https://www.federalreserve.gov/econres/notes/feds-notes/the-cross-border-trail-of-the-treasury-basis-trade-20251015.html',
 'Attribution and magnitude are correct. The claim omits the end date, net-versus-gross issuance and the calculation assumption; it does not show all marginal Treasury buyers are hedge funds.')
J(21,'MISLEADING','slr_exemption_market_causation',
 'Treasury/reserve SLR relief ran April 2020-March 31 2021. Fed August 2023 dealer analysis finds no significant change in dealer securities-financing activity during relief.',
 'https://www.federalreserve.gov/newsevents/pressreleases/bcreg20200515a.htm; https://www.federalreserve.gov/econres/notes/feds-notes/dealers-treasury-market-intermediation-and-the-supplementary-leverage-ratio-20230803.html',
 'Policy dates are right. Smooth while exempt/choppy on expiry treats coincident market conditions as a demonstrated SLR effect, omitting Fed purchases, reserves and other factors; hundreds of billions of bank holdings is not itself causal evidence.')
J(22,'MISLEADING','interest_revenue_historical_comparison',
 'Net interest/revenue: FY1979 9.2%, 1983 14.95%, 1985 17.64%, 1991 18.43%, 2024 17.88%, 2025 18.53%; 1979-85 long yields averaged about 11.6-11.7%.',
 RAW+'; FRED FYOINT, FYFR, DGS10, DGS30',
 'The lower-rate/higher-debt burden contrast has substance. The assertion that the last comparable revenue share was late 1970s/early 1980s omits the more directly comparable 1990s and confuses a period of rising rates with the actual ratio history.')
J(23,'TRUE','tenyear_yield_war_start',
 'DGS10 February 27 2026 3.97%; April 6 4.34%, up 37 basis points.',
 RAW+'; FRED DGS10; verify/EVENTS_2026.md war chronology',
 'Correct direction and starting range as of April 7. Daily closes establish the market observation, not its exclusive cause.')
J(24,'TRUE','warsh_first_fomc_june17',
 'Warsh took office May 22; June 16-17 2026 was the next scheduled FOMC meeting and his first as chair.',
 'verify/EVENTS_2026.md (permitted event scaffold); Federal Reserve FOMC calendar',
 'This is a scheduled first-chair meeting fact available June 15, not a claim about an already completed June 17 rate decision. Event scaffold was used as instructed and is not independent of all earlier research.', 'medium')
J(25,'MOSTLY_TRUE','sco_iran_declaration_september2026',
 'September 1 Bishkek SCO declaration condemned attacks on Iran; Chinese foreign ministry lists Xi, Putin, Modi and Sharif among participants.',
 'https://chn.sectsco.org/20260901/2493835.html; https://www.fmprc.gov.cn/eng/xw/zyxw/202609/t20260901_12014119.html',
 'The diplomatic event is supported. Picking a side is interpretation and almost no Western coverage needs a defined media sample; neither is established by the declaration itself.', 'medium')
J(26,'TRUE','oil_drop_march23_announcement',
 'WTI spot March 20 98.71 to March 23 89.33 = -9.50%; the move accompanied Trump ceasefire/de-escalation messaging.',
 RAW+'; FRED DCOILWTICO; verify/EVENTS_2026.md March chronology',
 'Roughly 9% is supportable for WTI over the immediate trading interval. This was a negotiation announcement, not proof a ceasefire had already taken effect.', 'medium')
J(27,'MISLEADING','russia_only_asian_alternative',
 'March reporting documents Asian interest in Russian oil and limited US sanctions relief; METI March 20 documents procurement cooperation for American crude.',
 'https://apnews.com/article/ea90f06d9f35fe4bb977f068d2c6ef27; https://www.meti.go.jp/english/press/2026/0320_001.html',
 'Several real policy developments are bundled with the false exclusivity implication that Russia is the one alternative seller. Other non-Hormuz suppliers existed; interest, sanctioned waivers and executed imports are different facts.', 'medium')
J(28,'UNVERIFIABLE','diesel_cracks_threefold',
 'September 9 EIA outlook shows sharply elevated distillate cracks, over $2/gallon in August-November; exact tripling depends on region, crude benchmark and starting observation.',
 'https://www.eia.gov/outlooks/steo/archives/sep26.pdf pp.6-7; https://www.eia.gov/outlooks/steo/archives/feb26.pdf',
 'The stress direction is well supported. The unnamed diesel refinery rate cannot be matched to an exact pre-closure/post-closure pair. A US, Singapore or European crack and a daily/period-average ratio are not interchangeable.', 'high')
J(29,'UNVERIFIABLE','emergency_oil_28_vs_8_13',
 'IEA April 14 documents a very large war-driven supply disruption; the three-country 2.8 mb/d spare/export-capacity sum is not reproduced.',
 'https://iea.blob.core.windows.net/assets/515f3128-df1a-4d6c-beb4-fd91d2434bef/-14APR2026_OilMarketReport_Free_version1.pdf; corpus/transcripts/jikh_2026-04-20_f353QO5Dgus.txt @8:08',
 'Capacity, incremental production, reroutable exports and Pacific transport are different quantities. Confirming the shortfall does not validate this sum. Eventual reserve exhaustion is an unresolved conditional forecast, not a completed fact.', 'high','mixed_data_and_prediction')
J(30,'MOSTLY_TRUE','bessent_aug24_sanctions_warning',
 'Treasury announced the campaign August 24; CNN direct press-conference clips support exclusion from the dollar system; contemporaneous reporting records delayed escalation and financial-system warning.',
 'https://home.treasury.gov/news/press-releases/sb0613; https://transcripts.cnn.com/show/cnc/date/2026-08-24/segment/09; https://truthout.org/articles/bessent-unveils-iran-sanctions-regime-he-admits-could-blow-up-global-economy/',
 'Core announcement, timing and warning check out. The entire stitched direct quotation was not available in one official transcript, so I do not mark verbatim wording fully verified.', 'medium')
J(31,'MOSTLY_TRUE','manufacturing_output_shares',
 'UNIDO yearbook figures broadly place China around 29-30%, US around 17% and Japan around 5-6% of world manufacturing value added.',
 'https://www.unido.org/sites/default/files/unido-publications/2024-11/YB-core-2024-yearbook-pdf.pdf',
 'The principal ranking and scale are supported. Year, current/constant dollars and Eurozone versus EU boundaries are unstated; the exact 15% Eurozone term was not independently reproduced and should not be treated as exact.', 'medium')
J(32,'MOSTLY_TRUE','oil_above_prewar_march26',
 'WTI February 27 66.96 versus March 25 91.51 = +36.7%; March 26 96.18 = +43.6%. Brent rose more.',
 RAW+'; FRED DCOILWTICO, DCOILBRENTEU',
 'Roughly 40% is reasonable for WTI around the video date. The crude grade and recording cut-off are missing; it is not a universal figure for all oil benchmarks.')
J(33,'UNVERIFIABLE','gromen_opec_gold_anchor_counterfactual',
 'Transcript attributes the gold-anchor/OPEC mechanism to Luke Gromen; no independently retrieved original source establishes the exact wording.',
 CORPUS+'jikh_2026-05-04_HcjbJvpKZIU.txt @6:32; searches of Luke Gromen/OPEC/gold material',
 'This is a counterfactual economic mechanism, not an observable necessity theorem. OPEC existence and oil price history cannot prove that a gold-backed reserve currency removes every reason for a cartel.', 'high','unverified_attribution_and_causal_theory')
J(34,'UNVERIFIABLE','gold_fomo_timing_advice',
 'Statement urges caution about timing and FOMO.',
 CORPUS+'jikh_2026-07-15_dFjvcY9Tth0.txt @29:30',
 'Normative advice and declared intent have no factual outcome to adjudicate. The transcript verifies the utterance but should not create a confirmed-fact hit.', 'high','nonfactual_recommendation')
J(35,'FALSE','fdr_gold_repricing_date',
 'Gold ownership/export restrictions and departure from domestic gold convertibility occurred in 1933; official revaluation from $20.67 to $35 was January 31 1934.',
 'https://www.federalreservehistory.org/essays/gold-reserve-act',
 'The explicit policy date fuses two separate steps. The economic magnitude is roughly right, but 1933 overnight repricing is contradicted by the official chronology.')
J(36,'MOSTLY_TRUE','hongkong_gold_storage_expansion',
 'Hong Kong May 2026 announcements targeted more than 2,000 tonnes within three years, compared with about 200 tonnes of existing capacity.',
 'https://www.info.gov.hk/gia/general/202605/27/P2026052600503.htm; https://www.news.gov.hk/eng/2026/05/20260507/20260507_131930_158.html',
 'The target scale is right and currently expanding can describe an active program. It should not be read as already completed 2,000-tonne storage; timing and multiple operators matter.')
J(37,'TRENDING','yuan_strengthens_late_march_may',
 'DEXCHUS 6.9116 March 27, 6.8980 March 31, 6.8145 May 19; fewer yuan per dollar means yuan appreciation.',
 RAW+'; FRED DEXCHUS',
 'The ongoing currency direction was correct as of the video. The claimed US purpose of the war and why the yuan moved remain interpretations, not established by the exchange rate.', 'medium','direction_with_unverified_cause')
J(38,'MOSTLY_TRUE','early2026_dollar_metals_oil_sequence',
 'Broad dollar index fell from 119.75 December 31 to 117.82 February 27; monthly gold rose 4309 December to 5020 February, before the March oil jump.',
 RAW+'; FRED DTWEXBGS, DCOILBRENTEU; World Bank monthly gold',
 'The broad chronology is supported. Massive speculative flows, silver-specific magnitude and a causal chain from dollar to metals to oil were not established by these price series.', 'medium')
J(39,'FALSE','centralbanks_stopped_treasuries_2014',
 'Foreign official Treasury holdings peaked above $4.1T in September 2015, after the claimed stop. Fed transaction research documents official net purchases and warns older TIC measures overstate official sales.',
 'https://www.stlouisfed.org/publications/regional-economist/first_quarter_2017/after-years-of-decline-yields-on-us-treasuries-rise; https://www.federalreserve.gov/econres/notes/feds-notes/estimating-u-s-cross-border-securities-flows-ten-years-of-the-tic-slt-20220218.html; https://fred.stlouisfed.org/series/BOGZ1FU263061130Q',
 'Central-bank diversification and a diminished aggregate bid are not equivalent to all central banks stopping Treasury purchases in 2014. The universal claim is contradicted; official foreign holders also are not exactly the central-bank universe.')
J(40,'MISLEADING','norway_treasury_80b_proposal',
 'September 1 NBIM letter proposed lowering government-bond share of the bond benchmark from 70% to 50%; approximately $80B US exposure reduction was an implication reported September 4.',
 'https://www.nbim.no/en/news-and-insights/submissions-to-ministry/2026/the-government-pension-fund-global--analyses-and-assessments-of-the-investment-strategy-for-bonds/; https://www.reuters.com/business/norways-2-trillion-sovereign-fund-proposes-deep-cuts-us-treasury-holdings-2026-09-04/',
 'An advisory benchmark proposal is presented as the fund already announcing an executed Treasury cut. The letter does not establish completed sales, anti-dollar motivation or an $80B transaction.', 'medium')
J(41,'TRUE','russia_september1_crypto_digital_ruble',
 'CBR July 21 2026 described crypto framework effective September 1; July 15 2025 rollout legislation scheduled large-scale digital-ruble introduction September 1 2026, phased by institutions.',
 'https://www.cbr.ru/press/event/?id=32724; https://cbr.ru/press/event/?id=25774',
 'Both announced legal dates were known before August 10. TRUE concerns enacted schedules, not proof that every Russian user or bank had a functioning CBDC by that date. Pilot work had already existed.')
J(42,'MOSTLY_TRUE','lagarde_digital_euro_quote',
 'ECB April 17 2026 statement contains the call to swiftly adopt digital-euro legislation; Lagarde is ECB President, not European Commission President.',
 'https://www.ecb.europa.eu/press/key/date/2026/html/ecb.sp260417~033a4546f5.sl.html',
 'Quote and policy position are accurate; the office attribution is wrong. It is inappropriate to turn the title error into denial that the quotation exists.')
J(43,'MISLEADING','genius_stablecoin_programmability',
 'GENIUS Act enacted July 18 2025 establishes payment-stablecoin regulation and lawful freeze/seizure compliance; it does not prescribe expiry, consumption categories or geofenced spending for all stablecoins.',
 'https://www.govinfo.gov/content/pkg/PLAW-119publ27/html/PLAW-119publ27.htm',
 'Tokens can be programmed, but a real law and generic technical possibilities are joined to imply a new universal money-control design. Bank-account money also can carry restrictions. Enactment alone does not establish the claimed cash/stablecoin contrast.', 'medium')
J(44,'UNVERIFIABLE','athene_227b_apollo_originated',
 'Myrmikan August 14 explicitly states $227B of Apollo deals in Athene US Life. Apollo filings establish affiliated origination, but do not reproduce this precise own-deals perimeter; $227B also appears as a prior total net-invested-assets measure.',
 'https://www.myrmikan.com/pub/Myrmikan_Research_2026_08_14.pdf p.16; https://ir.apollo.com/sec-filings/content/0001858681-26-000013/apo-20251231.htm; https://ir.athene.com/sec-filings/all-sec-filings/content/0001527469-24-000031/ath_agmer1q2024vf.htm',
 'Attribution to the intermediary is traceable, but independently validating total assets versus Apollo-originated, managed, affiliate and US-life-only assets requires a reconciliation not supplied. The matching historical total is not by itself proof of an error.', 'high')
J(45,'MOSTLY_TRUE','pe_owned_insurers_700b_134',
 'Myrmikan August 14 gives 134 life insurers and over $700B; NAIC year-end 2024 study reports 137 PE-owned US insurers across types and about $704.3B.',
 'https://www.myrmikan.com/pub/Myrmikan_Research_2026_08_14.pdf p.16; https://content.naic.org/sites/default/files/capital-markets-pe-owned-ye2024.pdf',
 'Source attribution and asset magnitude are supported. Life-only versus all-insurer counts explain a possible 134/137 difference; basically zero in 2009 is loose and not independently pinned to an exact baseline.', 'medium')
J(46,'MISLEADING','basel_nsfr_gold_real_money',
 'Basel NSFR assigns physical commodities including gold an 85% required stable funding factor; national implementation differed, including EU in 2021 and UK later.',
 'https://www.bis.org/committees/bcbs/basel-framework/standard/nsf?allChapters=true; https://www.gold.org/goldhub/gold-focus/2021/06/basel-iii-and-gold-market',
 'Stable funding is not synonymous with 100% cash backing or allocation of every gold liability. The rule can make intermediation more costly but does not prohibit unallocated gold or prove that its market can no longer operate at scale.')
J(47,'MOSTLY_TRUE','sec_data_center_abs_letter',
 'SEC staff July 29 2026 response to Latham concerns certain described data-center securitizations and the statutory ABS definition.',
 'https://www.sec.gov/rules-regulations/no-action-interpretive-exemptive-letters/division-corporation-finance-no-action/certain-data-center-securitizations-072926',
 'The response and quoted conclusion are real. July 29 is three weeks, not one week, before August 19; the opinion is limited to the structure described and is not a blanket exemption for AI loans.', 'medium')
J(48,'MOSTLY_TRUE','japan_crypto_tax_55_to20_proposal',
 'FSA February 2026 newsletter describes moving qualifying crypto gains from combined progressive taxation up to 55% to separate 20% taxation, conditional on legal changes and a later start.',
 'https://www.fsa.go.jp/en/newsletter/accessfsa2026/270.pdf pp.10-12; https://www.fsa.go.jp/en/refer/councils/singie_kinyu/20260216.html',
 'Correct as a proposal, not a tax cut already applying to all holders. Offshore wealth repatriation and yen support are inferred motives rather than verified outcomes or universal eligibility.')
J(49,'TRUE','cash_real_value_inflation',
 'For fixed nominal cash, real purchasing power is nominal balance divided by the price level; rising inflation accelerates its real-value decline.',
 'FRED CPIAUCSL via '+RAW,
 'Embedded economic identity is correct. Interest-bearing cash instruments require nominal interest and tax to be considered; the recommendation itself is not scored.', 'low','recommendation_embedded_fact')
J(50,'MISLEADING','cds_2007_six_month_stock_lead',
 'Broad equities peaked in October 2007, approximately three months after July; subsequent daily S&P peak-to-trough loss about 57% is often rounded to 60%. Shiller monthly averages give about 51%.',
 RAW+'; https://www.federalreservehistory.org/essays/great-recession-of-200709',
 'Rising credit stress preceded the severe equity bear market, but exactly six months requires selecting a later acceleration rather than the onset of falling prices. No CDS series or warning threshold is specified.', 'medium')
J(51,'TRUE','mmf_gdp_recession_comparison',
 'MMF/GDP 2026Q1 26.01%; 2000Q4 17.68%, 2007Q4 20.97%, 2019Q4 18.25%.',
 RAW+'; FRED MMMFFAQ027S and GDP',
 'All three comparisons hold even using Q1, the observation available before August 9. This is money-market fund assets, not all cash and not proof of future equity inflows or recession causation.')
J(52,'MOSTLY_TRUE','korea_population_retail_investors',
 'KSD end-2025 report released March 18: about 14.6M shareholders, overwhelmingly individuals, versus population around 51M.',
 'https://en.yna.co.kr/view/AEN20260318005500320?section=economy-finance%2Feconomy',
 'About fourteen million and roughly a quarter are reasonable approximations. Shareholders and active retail traders are different populations; ants is a common nickname, not universal self-identification.', 'medium')
J(53,'FALSE','us_pump_gasoline_50pct_march20',
 'AAA March 19 national regular gasoline $3.884 versus $2.929 a month earlier, approximately +32.6%, not 50%.',
 'https://southjersey.aaa.com/news/gas-prices-new-jersey-march-19',
 'For the implied US national pump-price comparison, the quoted increase is materially overstated. Oil futures or a selected local station cannot silently substitute for a pump-price aggregate.', 'low')
J(54,'MOSTLY_TRUE','dollar_purchasing_power_since2021',
 'CPI-based purchasing power fell about 59.7% January 1991-May 2026; peak CPI YoY in 2021-26 was about 9%, above the 1991-2020 maximum about 5.65%; May 2026 NSA inflation was 4.2%.',
 RAW+'; https://www.bls.gov/news.release/archives/cpi_06102026.htm; corpus/transcripts/bravos_2026-06-18_ArL4djz-76c.txt @1:35-2:27',
 'Read in full context, the 2021-22 acceleration and continuing elevated price level are real. Inflation did cool; it would be wrong to read this as claiming June 2026 instantaneous inflation exceeded 2022. The unspecific slope/trend-line language prevents an exact TRUE.', 'medium')
J(55,'MOSTLY_TRUE','real_gdp_two_to_three_percent',
 'Real GDP YoY 2023-25 mostly approximately 2-3%, with 2023Q3/Q4 about 3.23/3.39%; annualized quarter-on-quarter growth varied much more.',
 RAW+'; FRED GDPC1',
 'Broad recent growth characterization fits YoY data, but frequency is omitted and healthy is an assessment. Current raw GDP history is revised, so this is not a complete reconstruction of the April 8 release vintage.', 'medium')
J(56,'MISLEADING','fourteen_million_drive_two_korean_stocks',
 'End-2025 Korea shareholder count about 14.6M applies to the entire listed market; Samsung holders about 4.6M and SK Hynix about 1.19M before overlap.',
 'https://en.yna.co.kr/view/AEN20260318005500320?section=economy-finance%2Feconomy; corpus/transcripts/jikh_2026-07-20_hy90LdpEUvQ.txt @1:11',
 'A market-wide population is repurposed as the cohort driving two particular stocks. Neither the count nor general margin-debt growth establishes that these people mostly caused this rally with borrowed money.', 'medium')
J(57,'UNVERIFIABLE','cookunity_andre_discount',
 'The transcript records the offer; a dated August 10 affiliate landing-page capture was not retrievable.',
 'https://www.cookunity.com/andre (retrieval unavailable); corpus/transcripts/jikh_2026-08-10_Uw84lTiD5C8.txt @10:48',
 'A current generic promotional discount would not prove this code, its eligibility conditions or validity on the video date. Historical offer remains unverified, not false.', 'high','historical_commercial_offer')
J(58,'UNVERIFIABLE','bravos_call_capacity_scarcity',
 'No appointment-capacity ledger, booking velocity or dated full/available slot data is public in the reviewed material.',
 CORPUS+'bravos_2026-08-13_4AkB4c0tTfU.txt @10:29',
 'A recurrent urgency statement is observable rhetoric, but the underlying claim that slots fill quickly cannot be independently verified from an invitation to book.', 'high','private_operational_claim')
J(59,'UNVERIFIABLE','premium_members_reduce_sponsors',
 'Corpus/video catalog confirms member content and public premium pitches; economics and foregone sponsorships are not disclosed.',
 CORPUS+'jikh_2026-08-25_gVksaXViB4E.txt @30:13; corpus/videos.csv',
 'Existence of premium material is not evidence that membership revenue actually reduced sponsor count versus a counterfactual schedule. Personal protection advice and intentions have no resolved factual score.', 'high','mixed_product_and_private_causation')
J(60,'UNVERIFIABLE','webb_digital_feudalism_intent',
 'Video presents a Whitney Webb clip; no independently located full original interview fixes its context or the identity and intent of they.',
 CORPUS+'jikh_2026-09-02_NZpobX6MQVA.txt @13:13; searches for original Whitney Webb medieval-feudalism/digital-ID interview',
 'The embedded quotation is source rhetoric about intent, not documented adoption of a plan by specified decision makers. Attribution from the channel alone is not independent verification of the complete interpretation.', 'high','unverified_attribution_and_intent')
J(61,'MOSTLY_TRUE','kikoff_credit_builder_ad_claims',
 'Kikoff official page gives $5/month, no credit check/interest, 80% promotion; notes report +25 first month and +86 first year for selected sub-600 on-time cohorts.',
 'https://plus.kikoff.com/fb (especially terms 1-2)',
 'Advertiser terms broadly match. The +86 cohort also excludes new delinquencies/collections, omitted in the video; these are advertiser observational averages, not guaranteed or independently causal gains. Dated #1 App Store rank and exact Andre code were not verified.', 'medium','commercial_claim_with_selected_cohort')
J(62,'UNVERIFIABLE','aggressive_allocation_20_40_returns',
 'No specified investable rule, leverage limit, drawdown, fee schedule, holding horizon or public audited return series accompanies the 20-40% proposition.',
 CORPUS+'bravos_2026-06-11_zmIhCFYlBP0.txt @10:08-10:39',
 'Conditional marketing advice about possible returns does not establish attainable expected returns or the only route to them. Later assertion of model performance is a separate private-performance claim, not validation of this recommendation.', 'high','nonfactual_recommendation_and_performance_promise')
J(63,'MISLEADING','worldid_partners_universal_requirement',
 'World April 17 2026 announced Tinder, Zoom, Docusign and agentic-web integrations; partners describe tests/integrations, not an internet-wide mandatory credential.',
 'https://world.org/blog/announcements/the-new-world-id-and-the-partners-bringing-proof-of-human-to-the-internet; https://news.zoom.com/zoom-and-tools-for-humanity/; https://www.help.tinder.com/hc/en-us/articles/45145471604493-World-ID-for-age-verification',
 'Real partnerships and an ambition to provide proof of humanity do not verify that Altman said every internet transaction will require World ID. Voluntary integration, proof-of-human category and one compulsory identity provider are distinct.', 'medium')
J(64,'MISLEADING','operation_blackout_election_martiallaw',
 'Firsthand November 5 2019 FCW account describes bus attacks, a reset of election day, arrests and a plan to vote another day; it does not document martial law.',
 'https://www.nextgov.com/digital-government/2019/11/cyber-firm-sows-chaos-in-election-hack-simulation/238752/; corpus/transcripts/jikh_2026-09-02_NZpobX6MQVA.txt @10:28-11:21',
 'The bus detail identifies the November exercise, so a different July or London defender victory cannot refute it. Election suspension/reset is supported; cancellation plus military replacement of civilian government materially overstates the documented outcome. Absence from the account is not proof no participant ever suggested it.', 'medium')
J(65,'UNVERIFIABLE','jikh_cash_position_may4',
 'Self-report of unusually high cash alongside continuing investments; no independently verifiable holdings or usual-cash baseline.',
 CORPUS+'jikh_2026-05-04_HcjbJvpKZIU.txt @25:17',
 'The stated caution is an opinion and the allocation is private. Neither should be scored false for lack of public proof or true merely because it was said.', 'high','private_portfolio')
J(66,'UNVERIFIABLE','bravos_onecall_client_returns',
 'No client-level net-return sample, selection method, comparable baseline or independent audit.',
 CORPUS+'bravos_2026-08-13_4AkB4c0tTfU.txt @10:08',
 'Testimonials or existence of calls cannot establish persistent improved returns or causation from one consultation.', 'high','private_performance')
J(67,'UNVERIFIABLE','bravos_468pct_fiveyears',
 '468% cumulative growth implies approximately 41.5% annualized for exactly five years; no independently audited executable account history was found.',
 CORPUS+'bravos_2026-06-29_OZhbi8m1Mw8.txt @7:20; https://www.linkedin.com/posts/bravos-research_stockmarket-ai-investing-activity-7478050409140543488-sUlc',
 'The arithmetic is broadly compatible with a rounded 40% annual claim, not itself an inconsistency. Company repetition is not external verification of model execution, costs, survivorship, cashflows or live versus backtest status.', 'high','private_performance')
J(68,'UNVERIFIABLE','alpha_picks_micron_holding_2025',
 'Public price reporting supports MU approximately +239.1% during calendar 2025; Alpha Picks holding continuity and selection rationale require its dated recommendation/transaction ledger.',
 'https://www.zacks.com/stock/news/2812482/micron-up-239-in-2025-is-the-memory-chip-stock-still-a-buy-in-2026; https://help.seekingalpha.com/what-is-alpha-picks; corpus/transcripts/jikh_2026-08-05_dlaVKt9-Tfg.txt @10:34',
 'Stock performance is a corroborated subfact. It does not independently verify the sponsor held it through the selloff for the claimed reason or delivered that return to subscribers.', 'high','mixed_public_price_and_private_performance')
J(69,'UNVERIFIABLE','bravos_countless_clients_plans',
 'No defined countless denominator or independently documented before/after client cohort.',
 CORPUS+'bravos_2026-09-09_1ZS5_txbOsc.txt @19:17',
 'Offering a service is observable; the scale and effectiveness of client outcomes are not established by the sales statement.', 'high','private_client_outcomes')
J(70,'UNVERIFIABLE','bravos_report_price_caption',
 'Captions say $1.99 at 9:30; comparison price $2,000 and claimed saving $1,800 suggest a possible $199/$200 spoken price, but do not settle the audio.',
 CORPUS+'bravos_2026-05-15_7830S4NkFe8.txt @9:15-9:39',
 'Do not call a likely auto-caption ambiguity a proven deceptive offer. Original audio/checkout terms and the precise historical package are needed; neither $1.99 nor a corrected $199 is independently established.', 'high','transcription_and_historical_offer')
J(71,'UNVERIFIABLE','bravos_real_capital_returns',
 'The speaker says real-world and real-capital; no audited broker/custodian record demonstrates the model result was traded with capital.',
 CORPUS+'bravos_2026-06-18_ArL4djz-76c.txt @6:57; https://bravosresearch.com/youtube/the-most-dangerous-stock-market-trap-has-just-been-set/',
 'A backtest curve, model description or repeated company claim cannot verify actual implementation. Lack of public audit is not proof the assertion is false.', 'high','private_performance')
J(72,'UNVERIFIABLE','bravos_naturalresources_allocation',
 'Private assertion of significantly increasing exposure; portfolio weights, transactions and reference date absent.',
 CORPUS+'bravos_2026-04-27_PN8bHAr0f1M.txt @9:19',
 'Research coverage of natural resources is not evidence of executed firm or client allocation changes. Directional thesis and portfolio disclosure must be separated.', 'high','private_portfolio')

assert len(R) == len(claims) == 72
assert [r['claim_id'] for r in R] == [c['claim_id'] for c in claims]
assert len({r['claim_id'] for r in R}) == 72
assert set(r['verdict'] for r in R) <= {'TRUE','MOSTLY_TRUE','TRENDING','MISLEADING','FALSE','UNVERIFIABLE','OPEN'}
with (HERE/'second_reader_blind.csv').open('w',newline='') as out:
    w=csv.DictWriter(out,fieldnames=list(R[0]),quoting=csv.QUOTE_ALL);w.writeheader();w.writerows(R)
print(json.dumps({'rows':len(R),'verdicts':dict(collections.Counter(r['verdict'] for r in R)),
    'eligible':sum(r['accuracy_denominator_eligible'] for r in R)},indent=2))
