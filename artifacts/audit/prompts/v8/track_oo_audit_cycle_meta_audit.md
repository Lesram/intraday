# Track OO v8 — Audit-Cycle Meta-Audit (NEW LENS)

After 7 rounds and ~278 cumulative findings, **Track OO audits the audits**. What patterns has the cycle systematically missed? Where are the blind spots? What lens has V1-V7 NEVER applied? This is the most speculative track and exists to challenge the cycle's own assumptions.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `79b38fb`.

## Method

### 1. What V1-V7 NEVER tested

Read `artifacts/audit/MASTER_AUDIT_SYNTHESIS_v*.md` (or the V7 synthesis) and compile a list of *track types* used. Then ask:

- Has any version run a **chaos test** (kill the DB mid-trade; what happens)? If no → blind spot.
- Has any version run a **load test** (1000 concurrent WS messages; do alerts dispatch correctly)?
- Has any version tested **timezone edge cases** (DST transitions, ET-vs-UTC bugs at market boundaries)?
- Has any version tested **PnL accounting under wash sales / dividend ex-dates**?
- Has any version tested **Alpaca API failure modes** (5xx, rate-limit 429, malformed JSON, partial WS message)?
- Has any version tested **frontend/backend contract drift** (type mismatch, schema regression)?
- Has any version tested **observability failure** (Prometheus down → does the app crash, degrade, or silently lose metrics)?
- Has any version tested **database migration rollback** (apply, rollback, re-apply — does data round-trip)?
- Has any version tested **multi-day brain coherence** (restart 5 times, does state stay invariant)?

For each NO, that's a track-type V8 should propose for V9.

### 2. Finding-class distribution

Compile a histogram of finding classes across V1-V7:
- Security: N findings
- Data integrity: N
- Strategy logic: N
- Architecture: N
- Replay determinism: N
- Observability: N
- Performance: N
- Documentation drift: N
- ...

If a class has <5 findings cumulatively, the cycle may be UNDER-investing there. (E.g. if Performance has 0 findings, it's probably not because perf is perfect — it's because no track ever measured it.)

### 3. Finding-discovery latency

For each finding, when was it FIRST flagged vs when was it FIXED?

- Average latency between first flag and ship-of-fix?
- Are there findings flagged in V1 still open in V8? Why?
- Distribution of "fix didn't fix" findings (re-flagged in later rounds): which classes are most prone to this?

### 4. Same-class scan effectiveness

V6 W introduced same-class scans. Of the V7+V8 findings, how many were caught by a same-class scan vs found a fresh way?

If same-class scans catch <30% of related findings, they may need to be wider/smarter (e.g. semantic search, not just grep).

### 5. Test-vs-finding correlation

Does the audit cycle find MORE issues in modules with FEWER tests? Compute:

```
./venv/bin/python - <<'PY'
import pathlib, re
test_loc = {}
src_loc = {}
findings_per_module = {}  # populate from synthesis docs
for p in pathlib.Path("tests").glob("test_*.py"):
    target = p.name.replace("test_", "").replace(".py", "")
    test_loc[target] = sum(1 for _ in p.open())
for p in pathlib.Path("backend").rglob("*.py"):
    name = p.stem
    src_loc[name] = src_loc.get(name, 0) + sum(1 for _ in p.open())
# Print top-20 src files with low test-LOC ratio.
for name, sloc in sorted(src_loc.items(), key=lambda kv: -kv[1])[:20]:
    tloc = test_loc.get(name, 0)
    ratio = tloc / sloc if sloc else 0
    print(f"{name}\tsrc={sloc}\ttests={tloc}\tratio={ratio:.2f}")
PY
```

Modules with src/test ratio < 0.1 and historical findings > 5 = under-tested high-risk modules. Recommend prioritizing tests for V9.

### 6. Audit-cycle process meta-findings

- Are wave-PR commit messages getting MORE structured over time (good) or MORE bloated (bad)?
- Is the average wave-PR closing more or fewer findings than 1 year ago?
- Is the time-to-deploy-after-audit shrinking or growing?
- Are there findings that V1-V7 OPENED but later silently CLOSED without an explicit wave (i.e. lost track of)?

For finding-tracking integrity:
```
grep -rh "Finding-ID:\|finding=" artifacts/audit/v*_reports/ 2>/dev/null \
  | sort -u | wc -l
# vs
grep -rh "Closes:" docs/audit/* 2>/dev/null | wc -l
```

Mismatch = findings opened but never explicitly closed.

### 7. Recommended new lens for V9

Based on Sections 1-6, name 2-3 NEW track types V9 should run.
Examples (use freely if applicable):
- **Chaos engineering track** (kill -9 services, network partition).
- **Load track** (k6 / locust against `/api/*` while live trading).
- **Temporal-edge track** (DST, leap second, market-open second-precision).
- **API contract drift track** (frontend types vs backend pydantic).
- **Migration-roundtrip track** (apply, rollback, re-apply).

### 8. Recommended retirement of low-yield tracks

If a V1-V7 track type has yielded <3 findings cumulatively, recommend retiring it. Diminishing returns suggest the cycle is over-fitting the wrong dimensions.

## Output

`artifacts/audit/v8_reports/track_oo_audit_cycle_meta_audit.md` with:
- Section 1: Untested-domain list (with severity if user-facing)
- Section 2: Finding-class histogram + under-invested classes
- Section 3: Discovery-latency stats (median, p95, oldest-still-open)
- Section 4: Same-class scan hit rate
- Section 5: Under-tested high-risk modules table
- Section 6: Process meta-findings + finding-tracking integrity
- Section 7: 2-3 recommended new tracks for V9
- Section 8: Tracks to retire (if any)
- "Meta-findings: N. Recommended V9 tracks: N." + TL;DR

Quality bar: 3-6 findings. This track is the lowest-yield-but-highest-leverage. A single well-found "we've never tested X" finding can save 10 future audit rounds. End with one-paragraph summary.
