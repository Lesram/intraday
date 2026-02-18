# Evolving Organism Blueprint — 100% Completion TODO Tracker

**Source Blueprint:** docs/blueprints/EVOLVING_ORGANISM_BLUEPRINT.md  
**Created:** 2026-02-16  
**Purpose:** Actionable, ordered checklist to drive full blueprint closure with verification evidence.

---

## A) Immediate Compliance Gaps (from latest audit)

### A1. Regression threshold alignment (G-13)
- [x] Enforce `brain_N+1.sharpe >= brain_N.sharpe * 0.95` in multi-run regression tests.
- [x] Re-run organism regression suite.
- [x] Confirm pass evidence.

**Evidence:** `tests/test_organism_live_engine.py` updated and passing.

### A2. Blueprint marker taxonomy alignment (§10)
- [x] Add pytest markers in `pytest.ini`: `live`, `evolution`, `regression`.
- [x] Mark regression suite with `@pytest.mark.regression`.
- [x] Mark evolution suites with `@pytest.mark.evolution`.
- [x] Re-run marker-affected suites.

**Evidence:** `pytest.ini`, `tests/test_organism_live_engine.py`, `tests/test_self_evolution.py` updated; tests passing.

### A3. Feature-store integration path (G-08)
- [x] Ensure runtime scheduler passes `sessionmaker` into `OrganismLiveEngine`.
- [x] Validate no errors in scheduler/factory wiring.
- [x] Validate through focused tests.

**Evidence:** `backend/organism/scheduler.py`, `backend/api/factory.py` updated; tests passing.

### A4. Blueprint persistence proof tests (G-02/G-03/Phase 1)
- [x] Add tests proving dedicated files are written: `evolved_params.json`, `governance_state.json`, `regime_state.json`.
- [x] Add test proving load restores persisted governance/regime state containers.
- [x] Add test for brain quality-gate warning on invalid alpha-weight normalization.

**Evidence:** `tests/test_organism_blueprint_persistence.py` added; passing.

---

## B) Still Required for Full 100% Blueprint Closure

## B1. Long-duration live acceptance (§10.4, §10.6)
- [~] LT-06: 24h paper-execute run with brain save verification. (**started**)
- [~] LT-07: 5-day consecutive paper run with cumulative knowledge verification. (**started**)
- [ ] Archive logs/reports and map results to checklist items.

**Why pending:** Requires real-time wall-clock execution and active Alpaca paper environment.

### Active Run Metadata

- LT-06 background terminal id: `741837d9-3940-4056-9318-2a0bad961afe`
- LT-07 background terminal id: `e663e36c-5225-4527-acc2-9aafb63a81a8`
- Probe command base: `scripts/ci/run_organism_live_acceptance.py`
- Auth mode: dedicated audit account (`blueprint_audit_37c3c497@example.com`)

### Monitoring

- Check terminal output for active runs using terminal inspection tools.
- After each run ends, execute:
	- `venv/Scripts/python.exe scripts/ci/validate_organism_blueprint_100.py`
- Completion criteria for each run:
	- Duration meets blueprint minimum (`24h` for LT-06, `120h` for LT-07)
	- `error_probe_count == 0`

## B2. Formal full-checklist evidence bundle (§10.6)
- [ ] Produce single report containing pass/fail for each formal checklist line item.
- [ ] Include direct artifact references for each line item.
- [ ] Store under `docs/audits/` as release gate record.

## B3. Data-source compliance proof (“real data only”)
- [ ] Run and archive proof commands demonstrating no mock data in blueprint execution path.
- [ ] Attach env and runtime mode snapshot (`ALPACA_PAPER`, execution mode, scheduler state).

## B4. G-01 closure evidence (full bridge semantics)
- [ ] Document and test canonical production path that uses `OrganismLiveEngine` as the primary organism loop.
- [ ] Validate no divergence in critical logic between backtest and live decision chain.
- [ ] Add integration assertion around order-service feed + learner feedback + persistence cycle.

---

## C) Execution Order (Strict)

1. **Run extended-time deterministic full suite** (if required for zero-warning policy)
2. **Execute LT-06 24h paper run**
3. **Execute LT-07 5-day paper run**
4. **Generate formal checklist evidence bundle**
5. **Publish final 100% compliance sign-off report**

---

## D) Latest Validation Snapshot (Completed in this session)

- `venv/Scripts/python.exe -m pytest tests/test_organism_live_engine.py tests/test_self_evolution.py tests/test_organism_blueprint_persistence.py -q --tb=short`
- **Result:** `40 passed`

---

## E) Release-Gate Position (Current)

- Code-level blueprint integration: **high completion, materially improved in this session**
- Operational long-horizon blueprint acceptance: **pending real-time execution**
- Current status toward “100% blueprint completion”: **in progress, not yet final**
