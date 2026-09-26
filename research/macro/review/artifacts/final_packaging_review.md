# Final packaging QA

Reviewed the public-share boundary, README/run paths, latest unsealed Phase C/D/E text, and potential copied-source/credential exposure. This is a bounded content check; it does not repeat the prior all-file hash validation. Original source and sealed A/B files were not edited.

## Public bundle boundary

The repository `Lesram/intraday` is PUBLIC. Root was notified before publication and agreed to preserve the sealed local evidence while excluding extensive verbatim extraction artifacts from the public PR.

Recommended local-only paths, relative to review:

| Path | Why |
|---|---|
| `phase_a/directional_predicates.csv` | 818 transcript sentences, approximately 19,498 words. |
| `phase_a/pitch_sentences.csv` | 167 extracted sentences, approximately 3,290 words. |
| `phase_a/citation_like_sentences.csv` | 94 extracted sentences, approximately 2,288 words; longest excerpt 132 words. |
| `phase_a/contradiction_pair_sample.csv` | Duplicate source statements in the unadjudicated pair sample, 1,285 words. |
| `phase_a/contradiction_sample_adjudicated.csv` | The same source statements plus judgment columns; the authored report and curated table can carry the public conclusion. |

The 13,500-row `opposite_direction_candidate_pairs.csv` contains predicate IDs/dates, **not** copied sentences; it is not a bulk-text exposure. The curated contradictions table has short excerpts (943 words across 19 adjudicated pairs) with analysis, and `shared_10word_phrases.csv` has 580 words across 58 ten-word phrases; these are limited critical evidence rather than a transcript reconstruction. Root can retain those while omitting the bulk extraction files.

Phase C contains sampled short claim/prediction wording and authored judgments. Largest sampled claim is 60 words; no full transcript copies were found there. These samples support the blind-review audit. Do not exclude them merely because they contain quoted claims; they have a direct analytical purpose unlike publishing every extracted predicate.

Keep the public exclusions explicit in README/manifest validation. A local SHA seal may correctly list files deliberately absent from the public repository; an external reader must not be told the reduced public bundle alone reproduces that full local seal. Do not edit sealed evidence or silently rewrite its manifest to achieve publication.

## Credentials and local information

A targeted scan of 476 candidate review files, excluding dependency/build/cache/archive directories, found no private-key blocks, GitHub/AWS credentials, bearer-token literals or credential-bearing URLs. Apparent `sk-` matches all came from the same public **Elon Musk URL slug**, not an API key. Runtime snapshot/environment JSON inspection found no nonempty credential/account-ID fields. This is a targeted scan, not a guarantee about arbitrary secrets.

Eight unsealed review files contain local `/Users/…` paths, principally reproducibility logs, environment metadata and source-line links in the quantitative appendices. They expose the local username/path and do not resolve in GitHub's viewer. These are not authentication secrets. Prefer repository-relative links in a public-facing copy where practical; retain the exact local environment receipt if documenting that limited disclosure is acceptable. The portable dashboard is described separately and does not need the local source links to render.

The repository has pre-existing modified platform artifacts and unrelated untracked directories. Commit using the review-only path boundary; do not stage the entire workspace. The reviewed `.gitignore` already excludes local dependencies, node_modules, build intermediates, raw monitor cache/readings/attempts and screenshot artifacts. Root is implementing the additional source-text exclusions above.

## Reproduction and scope

- README commands are correctly relative to `research/macro/review/`. All named pipeline entrypoints and requirements exist.
- Snapshot reproduction/tests require the parent `research/macro/data/raw/` companion package; README discloses this dependency. The public PR should not imply that the companion source package is included.
- Live `monitor.py` uses fresh public FRED CSV endpoints. Dashboard rebuilding additionally requires Node and the installed Data compiler; `refresh.py` exposes explicit path overrides and fails if the compiler is absent. README/Phase E describe this limitation accurately.
- The self-contained HTML can be read without the source package, compiler or preview server. It remains a dated snapshot unless refreshed.
- No automatic scheduler, external distribution or brokerage execution is claimed. Monthly cadence and off-cycle rules are an operating specification, not a secretly installed automation.

## Final methodological observations

The previous material issues are repaired in the latest main report: the tail statistic is identified correctly, original truncation disclosure is acknowledged, numbered Markdown headings render, and the generated report's independence wording was flagged for alignment. The second-reader and prediction placeholders are now replaced with actual counts and explicit sampling limitations. Phase C does not turn the 16-case operationalization experiment into a population skill estimate or portfolio-return test.

Two small wording improvements remain useful:

1. The self-correction paragraph reverses the history of the tail-label mistake: the earlier text called **0.242 lower-tail**; the repair labels it two-sided and supplies the actual **0.12109 lower-tail** rank. The current numerical analysis is correct.
2. In concentration §6, prefer “two nonoverlapping completed five-year starts” to “two independent episodes.” Separation of return windows does not demonstrate independent economic regimes. The broader caveats already communicate the small-sample limitation.

No new blocking methodological flaw was found in Phase D/E or the completed result insertions. Public packaging is ready after the agreed bulk-transcript exclusions and corresponding companion-data disclosure are applied; the reviewer has not itself changed the publication set.

## Root resolution after QA

The five bulk extraction exclusions and PUBLIC_PACKAGE.md companion-data disclosure are implemented. The tail-statistic correction history and nonoverlapping-start wording are fixed. Local environment paths are retained as reproducibility metadata; they contain no credentials. The review-specific artifacts directory is explicitly unignored so the complete required receipt pack enters the PR.
