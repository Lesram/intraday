# Track CC v7 — Test Quality & Coverage (NEW SURFACE)

V6 W's behavioral/structural ratio was a 25/25/50 split — but that
counted *files*. Track CC measures **what code is actually exercised**
by the test suite, identifies coverage gaps, flaky tests, and slow
tests.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d44eace`.

## Method

### 1. Test inventory

- Total test count: `pytest --collect-only -q | tail -3` to get the count.
- File-level inventory: `find tests/ -name 'test_*.py' | wc -l`.
- Test classification:
  - Unit (single class / function)
  - Integration (multiple modules)
  - End-to-end (full tick / full replay)
  - Behavioral (revert-to-fail)
  - Structural (grep / inspect source)

Use `grep` heuristics: tests that use `inspect.getsource` are structural;
tests that construct objects + call methods + assert state are behavioral.

### 2. Line + branch coverage

Run `pytest --cov=backend --cov-report=term-missing` (if `coverage` is
installed; if not, document the gap and propose pinning). Capture:
- Overall % coverage
- Per-module % coverage (focus on `backend/organism/`,
  `backend/services/`, `backend/infra/`, `backend/api/`)
- Files with < 50% coverage
- Files with 0% coverage (zero direct test imports)

Compare to V3 Track M's "untested modules" list (composite_indicators,
ensemble_models, multi_timeframe, nightly_scheduler, training,
transfer_learning) — has the gap closed?

### 3. Mutation testing (if mutmut available)

`mutmut run --paths-to-mutate backend/organism/kelly_sizer.py` or similar.
A "killed" mutation is good (test catches the change). A "survived"
mutation is a coverage gap.

If mutmut isn't installed: document and propose. If it is: run on 1-2
critical modules (kelly_sizer, walk_forward) and report kill rate.

### 4. Flaky test detection

Run the curated suite **3 times in a row**:
```
for i in 1 2 3; do
    ./venv/bin/python -m pytest tests/ --timeout=15 -q --tb=no -p no:warnings 2>&1 \
        | tail -3 \
        | tee -a artifacts/audit/v7_reports/cc_flaky_run_$i.log
done
```

Tests that pass twice and fail once (or vice versa) are flaky. List them.
Memory.md notes "4 flaky async tests pass individually, fail in full suite"
— still true?

### 5. Slow-test inventory

`pytest --durations=20 tests/` — capture the 20 slowest tests. Threshold:
> 1 second is a candidate for review.

### 6. Test interdependency

- Tests that share fixtures across files (via conftest) — do any leak state?
- Tests that mutate `os.environ` without `monkeypatch` (V5 had a few of these).
- Tests that assume DB / Redis / running container — list them.

### 7. Error-path coverage

For each `raise` statement in `backend/organism/`, find the matching
test (or note the gap). V3 Track M-12 already added 3 negative tests
for `replay_simulator.py` ValueError sites; extend the audit.

`grep -rn "^        raise " backend/organism/ | wc -l` — current count.
Fraction with explicit test = the deliverable.

### 8. Async test correctness

- `pytest-asyncio` mode: `auto`? per `pytest.ini`?
- Tests that should be `async` but aren't (calling coroutines synchronously)?
- Tests with `asyncio.run` vs `pytest-asyncio` fixtures — consistency?

### 9. Test smell catalog

Sample 20 random tests; classify smells:
- Missing assertions ("test runs but asserts nothing")
- Over-mocking (stubs out the very thing under test)
- Long setup (> 30 lines) without fixtures
- Test interdependency (test_b assumes test_a ran)
- Brittle string matching (V6 W flagged these)

### 10. Performance of the test suite

- Total CI test runtime estimate (sum of durations).
- Top 5 modules by test runtime.
- Recommendation: parallelize via `pytest-xdist`?

## Output

`artifacts/audit/v7_reports/track_cc_test_quality.md` with:
- Test inventory + classification
- Line + branch coverage by module
- Mutation kill rate (if applicable)
- Flaky test list
- Slow-test top-20
- Test interdependency cases
- Error-path coverage fraction
- Async correctness audit
- Test smell catalog (20 sample)
- Suite performance recommendation
- "Coverage gaps: N modules below 50%; flaky tests: N; slow tests: N"

## Constraints

Read-only on production code. May install `coverage` or `mutmut` into
the venv if not present (document any pip install).

## Quality bar

This track's deliverable is a comprehensive test-quality report. Expect:
- 5-15 modules below 50% line coverage
- 0-5 flaky tests
- 5-10 slow tests
- 3-8 test smells per 20 sampled

End with a one-paragraph summary of the suite's overall health and the
single highest-leverage improvement.
