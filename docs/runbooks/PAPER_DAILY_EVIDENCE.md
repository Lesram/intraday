# Manual paper daily evidence

This runner collects real paper-broker and local observer responses using GET only. It produces a private immutable evidence pack, not a trading action, installed schedule, operational certificate or capital-promotion authorization. Run after the authoritative calendar close plus five minutes. The same command on holidays produces `NO_SESSION`; future dates, incomplete inputs and unmet quality conditions produce `BLOCKED`.

## Required inputs

Use the actual operating checkout as `--root`, including its mounted brain and log directories. Supply:

- `--freeze`: approved active host `param_freeze.json`. Never generate a new freeze to satisfy this report.
- `--activation`: immutable cutoff approval/activation manifest, including the approved freeze hash, cutoff and verified flat/no-open-order state. This remains the original measurement boundary across later repairs.
- `--release`: separately approved identity of the *currently deployed* release. Required JSON fields are `source_sha`, `image_sha`, `image_digest`, `runtime_config_hash`, and `timeframe`. The observer's `image_sha` commonly equals the source SHA; `image_digest` is the actual immutable Docker image digest. Do not substitute one for the other. If qualified forward entries span several approved releases, `approved_entry_identities` may contain their reviewed `{source_sha,image_sha,runtime_config_hash}` identities. This is a reviewed release inventory, not permission to whitelist an unexplained mismatch.
- `--baseline-dir`: original activation brain backup directory containing `backup_manifest.json` and `trade_history.csv`. Its manifest hash must match `activation.historical_baseline.manifest_sha256` when explicitly present, otherwise the older schema's `activation.backups.brain.manifest_sha256`; its ledger checksum/length must match the backup receipt. A new activation can retain the original historical baseline while recording a distinct fresh recovery backup under `backups.brain`. Only an unchanged prefix of the original ledger can exempt known historical rows with missing dates. No baseline means unscoped rows block the verdict.
- Current paper credentials in `ALPACA_API_KEY_ID`/`ALPACA_API_SECRET_KEY` (legacy alternate names supported), and a previously issued read-only observer token in `INTRA_MONITOR_TOKEN`. The runner does not read `.env`, print tokens, request tokens or issue POST requests. Use the existing authorized credential mechanism; do not put secrets in command arguments, reports or Git.

The root must expose the new exact-accounting policy and the entry-receipt observer before new forward trades can qualify. A previous release is expected to produce `BLOCKED`, not a retrospective pass.

```sh
PYTHONPATH=. venv/bin/python scripts/ops/paper_daily_evidence.py \
  --session 2026-09-21 \
  --root /absolute/path/to/operating/intra \
  --freeze /absolute/path/to/active/param_freeze.json \
  --activation /absolute/path/to/activation_manifest.json \
  --release /absolute/path/to/approved_release_identity.json \
  --baseline-dir /absolute/path/to/activation/brain-backup \
  --output /absolute/path/to/private/daily-evidence
```

For old text logs without timezone offsets, add `--log-timezone` with the verified logging timezone. Never assume the host timezone equals the API container's timezone. Structured logs already contain UTC timestamps.

## What is collected and checked

The endpoint is fixed to `https://paper-api.alpaca.markets`; redirects and environment HTTP proxies are refused. Local observer requests are fixed to `http://127.0.0.1:8000/api/v1/paper-monitor/{deploy,organism/status}`. A narrowly formatted Docker inspection reads only the known API container's name, immutable image digest and Compose identity. It never prints environment variables or container commands.

Order collection includes all statuses and unfilled orders. Any forward order marked `replaced`, including a zero-fill predecessor, blocks the quality verdict as `replacement_execution_lineage_unverified`: the current feed cannot prove complete replacement chains or distinguish cumulative summaries from incremental fills. Such rows remain in the inventory; they are never certified by summing replacement summaries. The first descending page has an exclusive capture-time upper bound; subsequent pages use exclusive `before_order_id`, with no incompatible time filter. Submission-time ties remain traversable through order identities. Duplicates, nonchronological pages, ignored/nonadvancing cursors, response/schema errors and the 100-page limit block completion. Termination requires a short page or crossing the verified flat activation cutoff. A final newest-order probe and position check detect concurrent trading during collection. Raw GET bytes, parameters and hashes are retained so completeness is recomputed on replay instead of trusted from a `complete=true` assertion. [Alpaca order API contract](https://docs.alpaca.markets/us/reference/getallorders-1)

Local files must be regular files with one hard link and no symlink in any path component. Supply canonical paths (for example, `/private/tmp` rather than the macOS `/tmp` symlink). The reader traverses pinned directory descriptors without following links, refuses nonregular files without waiting on FIFOs, and checks opened-file identity/link-count/size/mtime/ctime before and after reading. Each file is read once into the pack, with a complete `application.log*` inventory. A changing input set blocks review. Analysis uses those exact bytes, including failed-run partial inputs. The live brain and original history are never rewritten.

The authoritative close checkpoint checksum and policy must verify; pending closes or mismatch with the rounded CSV projection block results. Exact entries, all exit legs, quantities, cost basis and PnL reconcile through the existing Decimal reconciler. `db_fill` is a legacy approximation and does not qualify; complete accounting uses `db_position_fills`.

The entry receipt joins the database entry ID to the actual broker client order ID, then to its exact reconstructed cycle. It checks approved source/image/config identity, feed/timeframe, passed-gate frame timestamps/order, and a nonnegative bar age no greater than 120 seconds at submission. Receipt directions and ages must be finite JSON numbers; frame rows, requested shares and tick counters must use the producer's integer types with valid ranges. Boolean/string coercions, NaN/Infinity and malformed frame hashes are rejected; this strict receipt rule does not rewrite inherited historical checkpoint values. The frame hash identifies the observed features but does not replace an archived provider dataset or prove a trading edge. Identical repeated receipt lines do not become independent trades; conflicting identities block the pack. Every buy in a multiple-buy/pyramid cycle needs its own unique receipt, exact client-order join and the same freshness/context checks; an anchor receipt cannot certify subsequent adds. Missing, reused or stale scale-in receipts withhold the entire cohort verdict.

Successful engine tick logs must span the requested session with no gap over 120 seconds and no unparseable log records or reported tick errors. Boundary timestamps alone are insufficient. This is observed tick coverage, not a proof of uninterrupted host availability or every execution path. All log rotations are inventoried; missing logs and unknown timezones remain explicit.

## Results and limitations

- `READY_FOR_REVIEW`: collection, accounting, entry evidence and session coverage pass these bounded checks. The native strategy gate is evaluated with **explicit 6 bps round-trip costs**, retaining its existing 60/120-trade looks. The runtime cost setting is unchanged. This is not whole-platform or unattended-operation acceptance.
- `BLOCKED`: reasons and questionable rows remain visible; strategy output is `WITHHELD`, even if a statistic could look favorable. No losing row is silently excluded to improve the result.
- `NO_SESSION`: the successful broker calendar query returned no session for that date. This does not count toward successful market-session acceptance.

A verified no-trade day needs complete flat broker evidence, clear accounting and observed full-session tick coverage. Its native strategy result stays `INSUFFICIENT`; active order/partial-exit/flatten paths remain unobserved. A report for an earlier date collected with today's broker state is blocked because current positions cannot attest historical flatness. Replay the pack collected on that day instead.

The native cohort is cumulative from the approved cutoff. No automatic strategy rule or statistical eligibility is changed. Shadow-event counts are diagnostic observations, not independent trades. Old missing entry receipts, unapproved identities, stale input frames, unqualified compound entries or missing log coverage remain unresolved until evidence exists; do not fabricate receipts or edit history.

Exit codes: `0` for `READY_FOR_REVIEW`/`NO_SESSION`, `1` for a published `BLOCKED` pack, `2` for invalid credentials/arguments or unsafe/unavailable output. Failure before enough inputs are available may produce no pack and is not a successful session.

## Immutable publication and replay

The directory is `OUTPUT/SESSION/CONTENT_HASH/`, containing `manifest.json`, `report.json`, and exact inputs. Identical evidence/options/results reuse the pack; changed evidence creates a new revision, never overwriting a previous result. Publication uses pinned no-follow directory descriptors, a temporary directory and an atomic relative rename; swapped directory symlinks cannot redirect its writes into the brain, and an interrupted build cannot leave a complete-looking final directory. Input/brain aliases, including symlinked brain roots and hardlinked input files, are refused. Files may contain private account/order identifiers; keep real packs local/private and do not attach them unredacted to public PRs.

```sh
PYTHONPATH=. venv/bin/python scripts/ops/paper_daily_evidence.py \
  --session 2026-09-21 \
  --replay-pack /absolute/path/to/private/daily-evidence/2026-09-21/HASH \
  --output /absolute/path/to/separate/replay-output
```

Replay validates every input checksum and recomputes collection and quality checks without network access. The CLI labels the result as replayed; it is not a new broker observation. The local receipt is reproducible evidence, not a cryptographically signed broker attestation.

The standalone `standdown_session_row.py` remains diagnostic only. Its `--force` cannot create completed-session evidence. Prefer the daily runner's stored diagnostic and authoritative broker calendar for acceptance.

## Reviewed actual-host execution

`scripts/ops/paper_daily_host.py` is the credential adapter for the installed host. It authenticates the existing private observer account locally, verifies that its returned role is exactly `paper_monitor`, and obtains paper credentials from the running API container inside the same process. Docker inspection is restricted to that known container's identity, labels and environment; neither credentials nor the environment are printed, written into packs or put in process arguments. The only POST is local observer login. All broker requests use the existing fixed-paper GET transport with redirects and proxies disabled. The wrapper neither recovers services nor sends notifications.

Before installation, retain the original activation's `backup_manifest.json` and `trade_history.csv` together in a private directory outside `organism_brain_archive/` and the operating checkout. Preserve their exact bytes and keep the directory mode `0700`; do not generate a replacement receipt. Automated 30-day archive pruning must never remove the daily report's baseline. The wrapper verifies the original activation, current activation and retained manifest all name the same original baseline hash, plus the ledger's checksum and length.

Create a reviewed binding at `~/Library/Application Support/Intra/daily-evidence-binding.json`, owned by the operator with mode `0600`. This document is also the collector's release identity. It pins the **new explicitly approved** policy-lock cutoff and freeze without rewriting the original activation or historical learner counters. The following is a schema example with placeholders, not an approved release:

```json
{
  "schema": "paper_daily_host_v1",
  "approval_reference": "Recorded operator approval and accepted release",
  "approved_at": "APPROVED_UTC_TIMESTAMP",
  "measurement_cutoff": "NEW_APPROVED_FROZEN_AT",
  "source_sha": "40_CHARACTER_SOURCE_SHA",
  "image_sha": "40_CHARACTER_IMAGE_SOURCE_SHA",
  "image_digest": "sha256:64_CHARACTER_DOCKER_DIGEST",
  "runtime_config_hash": "VERIFIED_RUNTIME_CONFIG_HASH",
  "timeframe": "1Min",
  "operator_control_path": "/app/data/operator_control_state.json",
  "effective_policy_hash": "64_CHARACTER_REVIEWED_PARAMETER_HASH",
  "root": "/Users/marselkei/VS/intra",
  "output": "/Users/marselkei/Library/Application Support/Intra/daily-evidence",
  "freeze": {"path": "/absolute/path/to/new/param_freeze.json", "sha256": "EXACT_FILE_HASH"},
  "activation": {"path": "/absolute/path/to/new/activation_manifest.json", "sha256": "EXACT_FILE_HASH"},
  "original_activation": {"path": "/absolute/path/to/original/activation_manifest.json", "sha256": "EXACT_FILE_HASH"},
  "policy_baseline": {"path": "/absolute/path/to/research_policy_baseline.json", "sha256": "EXACT_FILE_HASH"},
  "baseline": {"path": "/absolute/path/to/private/retained-original-baseline", "manifest_sha256": "ORIGINAL_RECEIPT_HASH"}
}
```

The cutoff must match both the approved freeze and current activation receipt. The activation must attest a verified paper endpoint, zero positions and zero open orders. Its explicit `historical_baseline` points to the preserved original history; its `backups.brain` may contain a different fresh recovery snapshot. The policy artifact's canonical parameter hash must equal `effective_policy_hash`; its exact file hash, including the approved model fingerprints and prediction context, must match the freeze's `effective_policy_baseline.artifact_sha256`. The observer must report the exact approved source, image-source and runtime-configuration identities; Docker must report the approved immutable image and exact Compose project/service. The engine's observed `policy_lock` must say `locked=true`, `automatic_promotion_enabled=false` and `frozen_models=true`, with identical effective parameter values/hash. Its startup `baseline` receipt must report `configured=true`, `verified=true` and the exact approved policy artifact SHA-256. Matching parameter values alone cannot certify unpinned models. ML influence must be off and fixed-risk sizing on. Missing fields never inherit reassuring defaults. Policy is checked again against the collector's captured status before statistical analysis.

Run the adapter manually only after the approved release and binding are installed:

```sh
./venv/bin/python -B scripts/ops/paper_daily_host.py \
  --binding '/Users/marselkei/Library/Application Support/Intra/daily-evidence-binding.json'
```

The default session date is today's US Eastern date. `--session YYYY-MM-DD` is available for an explicit same-day check; past sessions require immutable offline replay instead. An invocation before calendar close plus five minutes is blocked. A confirmed holiday produces `NO_SESSION`. A private per-output lock excludes overlapping invocations. Every invocation with a valid binding/output writes a private receipt under `OUTPUT/host-runs/`, including blocked authentication or collection attempts. Invalid bindings and duplicate invocations report their failure on stdout without fabricating a completed pack. Exit `0` means `READY_FOR_REVIEW` or `NO_SESSION`; exit `1` means attention is required. These outcomes never authorize trading or automatic promotion.

`ops/launchd/com.intra.paper.daily-evidence.plist` is a separate, deployment-ready template; adding the file does **not** install it. It runs daily at **13:10 Mac local time**, intended for the verified America/Los_Angeles host: 20:10 UTC during PDT and 21:10 UTC during PST. This is ten minutes after a regular session close; early closes are also handled by the broker calendar. `RunAtLoad` is false, so installation does not accidentally run a pre-close report. No credentials are embedded in the template. Keep the existing five-minute recovery watchdog and backup schedules unchanged.

Installation belongs to the reviewed deployment step: copy the accepted script/dependencies, pin and validate the final binding, ensure the output and Application Support directory are private, precreate `daily-evidence-job.log` with mode `0600`, then load the template in the logged-in user's LaunchAgents. Verify the loaded schedule, manual exit code, receipt and resulting immutable pack. A logged-in, awake Mac, working Docker and available observer/broker endpoints are required. A missed run after logout/power-off cannot be reconstructed from the next day's current broker state. The job has no automatic recovery, retry or notification mechanism; its launchd exit status, private job log and run receipts must be reviewed after close. Correct a reported cause and rerun while it is still the same Eastern session date; retain every failed receipt and earlier pack.


The reviewed host binding also pins `operator_control_path` to
`/app/data/operator_control_state.json`, matching the expanded freeze. The
corresponding host file is `ROOT/data/operator_control_state.json`. Checks compare
its checksum, manual latch, reason and timestamp with actual engine governance.
The checksum is observed each run, not permanently pinned to the initial resumed
state: an operator halt is legitimate and must survive monitoring, restarts and
brain recovery. A missing/corrupt record, control fault, status mismatch or
unconfigured persistence blocks acceptance. Monitors never modify this file.
