# Independent second reader: pre-unblinding record

All 72 sampled claims were individually read and judged before access to the original verdicts. The output is `second_reader_blind.csv`; `second_reader_write_judgments.py` records the 72 explicit manual decisions and serializes them. It is not a rule-based classifier. The accompanying SHA-256 seal fixes these decisions before comparison. This note is also sealed and will not be revised after unblinding.

## Blinding and coverage

The reader saw `blind_claims.csv`, the original verification protocol, raw numerical histories through `scripts/factbase.py`, original transcript material and public evidence. The sample contains eight claims from each of nine input packages, 72 unique IDs. Full transcript context had been read in Phase A by the blinded reading team; targeted passages were reopened where wording or context affected an individual judgment. No prior verdict CSV, verification output, Brief 001, earlier report or other Phase C finding was opened before this seal. Phase A/B documents were not changed.

The permitted `verify/EVENTS_2026.md` scaffold contains some prior interpretations and was not a pristine independent source. I used its event chronology for the war and first Warsh meeting, not its evaluative framing. Independence here means label-blind procedural review, not a different model family, a different dataset or wholly independent discovery of every event. All web retrieval occurred September 20, 2026 UTC; claims were judged against the video date, with later pages used only where they preserve an earlier observation or publication. A live page is not automatically an archived as-of snapshot.

## Judgment conventions

The seven protocol tokens were preserved. Counts before comparison are TRUE 10, MOSTLY_TRUE 21, TRENDING 1, MISLEADING 13, FALSE 3, UNVERIFIABLE 24 and OPEN 0. Thus 32 are provisionally supported and 16 adverse among 48 rows with a resolved factual label; 24 remain outside that denominator. This is a description of this reader's judgments, **not a 66.7% truth probability** or a population estimate. Package weighting and inter-reader comparison occur only after the seal.

The CSV's `accuracy_denominator_eligible` flag implements the protocol's resolved-label denominator. It does not mean all eligible items have equal epistemic content. `adjudication_scope` explicitly distinguishes attribution-only judgments, recommendations with embedded facts, private performance, broad causal interpretations and ordinary data facts. In particular, the Musk and Lynch quotes can be accurately attributed without proving the speakers' empirical or normative propositions. Counting these alongside measured prices obscures that difference.

Composite claims were not automatically judged by their strongest or weakest fragment. The note records the supported core and the unsupported addition. A substantive scope/unit substitution is MISLEADING; a minor timing/detail omission with a supported central statement is MOSTLY_TRUE. An unavailable underlying series or portfolio ledger is UNVERIFIABLE, not FALSE. Advice without an operational outcome remains UNVERIFIABLE and excluded rather than being rewarded as true. Future policy **schedules already enacted** are checkable as schedules; their eventual implementation is not silently treated as accomplished. No sampled row required OPEN as its final dominant classification, although the oil-reserve claim contains an unresolved predictive facet.

## Important context checks

- The FTSE/S&P claim uses a real FTSE rule to imply S&P had also changed: S&P's June 4 release explicitly retained the IPO seasoning rule one day before the June 5 video.
- Auction yields and daily constant-maturity yields are different series. The 30-year auction record is corroborated; the neighboring broad borrowing-cost statement receives a contextual qualification rather than an automatic false verdict based on DGS30.
- “The ECB stepped in in 2011” does not say it **first** intervened in 2011. Adding that word would manufacture a chronology error.
- The Operation Blackout bus episode matches the **November 5, 2019** exercise. Its firsthand account describes restarting the election, while July and London exercises had different outcomes. A different exercise cannot refute this one. The unsupported martial-law addition remains material.
- The CPI paragraph acknowledges cooling inflation and identifies the acceleration beginning in 2021. It should not be judged as though it unambiguously claimed the current monthly pace exceeded 2022.
- A 468% cumulative five-year gain is about 41.5% annualized. It is broadly compatible with a rounded 40% annual figure; that arithmetic does not prove a live track record.
- The $1.99 report price may be an auto-caption error. The arithmetic suggests a different spoken price but cannot resolve audio or historical checkout terms.

## Evidence limits and reproducibility

`second_reader_data_checks.py` uses the permitted raw snapshot and factbase for dated prices, yields, nominal fiscal ratios, GDP, CPI, money-market funds, gold and historical drawdowns. Its JSON preserves measured observations and calculations. It does not import any sealed Phase A/B analysis. The raw histories are generally revised snapshots, not a complete ALFRED vintage archive; GDP and other subsequently revised figures carry that limitation. Money-market/GDP comparison deliberately uses Q1 2026 so a later Q2 release is not smuggled into the August 9 information set.

The available Shiller earnings series ends in June 2023 even though its price column extends much later. The current equity/cash relative-value claim was therefore left UNVERIFIABLE rather than calculated with stale earnings. Historical sector-return definitions, exact diesel crack benchmarks and incremental oil spare/export capacities were likewise not invented to complete missing calculations.

Primary government, issuer, researcher and publisher records were preferred. Some direct sources could not be retrieved: the Treasury auction PDF, an original Goldman workbook, a historical CookUnity affiliate landing page and private recommendation/performance ledgers. The affected CSV rows disclose secondary corroboration or remain unverified. A number repeated by an intermediary was not automatically treated as independent confirmation. Apollo/Athene's $227B perimeter is specifically unresolved; its resemblance to an earlier total-assets figure is insufficient to prove the channel's claim false.

There was no external source search establishing private Bravos client outcomes, holdings or actual trading capital. Public channel repetition, model curves and service advertisements cannot fill that gap. The Alpha Picks claim contains a checkable stock return but a separately unverified holding/rationale claim. Sponsor credit-score statistics are identifiable company-selected cohorts and are not causal guarantees.

The review is a bounded independent re-adjudication of 72 supplied atoms. It is not a complete new extraction of the corpus, an exhaustive search of all public archives, or a claim that every unresolved proposition is unknowable in principle. Sources, dates, measurement conventions, uncertainty and the needed missing evidence are carried row by row so disagreements can be adjudicated rather than counted automatically as errors by either reader.
