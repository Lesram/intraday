# Manual paper daily evidence

This runner collects real paper-broker and local observer responses using GET only. It produces a private immutable evidence pack, not a trading action, installed schedule, operational certificate or capital-promotion authorization. Run after the authoritative calendar close plus five minutes. The same command on holidays produces `NO_SESSION`; future dates, incomplete inputs and unmet quality conditions produce `BLOCKED`.

## Required inputs

Use the actual operating checkout as `--root`, including its mounted brain and log directories. Supply:

- `--freeze`: approved active host `param_freeze.json`. Never generate a new freeze to satisfy this report.
- `--activation`: immutable cutoff approval/activation manifest, including the approved freeze hash, cutoff and verified flat/no-open-order state. This remains the original measurement boundary across later repairs.
- `--release`: separately approved identity of the *currently deployed* release. Required JSON fields are `source_sha`, `image_sha`, `image_digest`, `runtime_config_hash`, and `timeframe`. The observer's `image_sha` commonly equals the source SHA; `image_digest` is the actual immutable Docker image digest. Do not substitute one for the other. If qualified forward entries span several approved releases, `approved_entry_identities` may contain their reviewed `{source_sha,image_sha,runtime_config_hash}` identities. This is a reviewed release inventory, not permission to whitelist an unexplained mismatch.
- `--baseline-dir`: original activation brain backup directory containing `backup_manifest.json` and `trade_history.csv`. Its manifest hash must match `activation.backups.brain.manifest_sha256`; its ledger checksum/length must match the backup receipt. Only an unchanged prefix of that ledger can exempt known historical rows with missing dates. No baseline means unscoped rows block the verdict.
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
