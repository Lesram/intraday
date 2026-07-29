"""Brain-volume isolation guard (2026-07-23 ops work order follow-up).

Un-isolated test runs mutate the REAL organism_brain/ Docker volume — this has
destroyed data twice (qty=0 shadow-telemetry pollution; four 07-07 corrupt-head
forensic dirs evicted via the keep-5 retention cap on 2026-07-23). tests/conftest.py
now redirects ORGANISM_BRAIN_DIR to a scratch dir at module level, BEFORE any test
module imports live_engine (which reads the env at import into BRAIN_DIR).

These probes fail loudly if that protection regresses.
"""

from __future__ import annotations

import os
from pathlib import Path


def test_brain_dir_env_is_redirected_away_from_real_volume():
    """conftest must have pointed ORGANISM_BRAIN_DIR somewhere safe."""
    val = os.environ.get("ORGANISM_BRAIN_DIR")
    assert val, "ORGANISM_BRAIN_DIR must be set for the test session"
    resolved = Path(val).resolve()
    real = (Path(__file__).resolve().parents[1] / "organism_brain").resolve()
    assert resolved != real, (
        "ORGANISM_BRAIN_DIR points at the REAL organism_brain volume — test "
        "isolation regressed; un-isolated runs corrupt live brain state."
    )


def test_live_engine_import_time_brain_dir_is_isolated():
    """live_engine.BRAIN_DIR is captured at import — verify the import-time value
    (what default-constructed engines/brains actually use) is not the real volume."""
    from backend.organism.live_engine import BRAIN_DIR

    resolved = Path(BRAIN_DIR).resolve()
    real = (Path(__file__).resolve().parents[1] / "organism_brain").resolve()
    assert resolved != real, (
        "live_engine.BRAIN_DIR resolved to the real organism_brain volume. "
        "Either conftest's redirect ran too late (after live_engine import) or "
        "it was removed. Default-constructed engines would write live state."
    )
    # And the scratch dir is actually usable.
    resolved.mkdir(parents=True, exist_ok=True)
    probe = resolved / ".isolation_probe"
    probe.write_text("ok")
    probe.unlink()


# ── Punchlist 2026-07-24 item 3: bare-constructed components honor the env ──
# DiagnosticReportStore and TransferLearningEngine used to hardcode
# brain_dir="organism_brain", bypassing ORGANISM_BRAIN_DIR entirely — the
# conftest shield could not cover a future test constructing them bare. Their
# defaults now resolve the env lazily; these probes pin that behavior.


def test_bare_diagnostic_store_lands_in_scratch(tmp_path, monkeypatch):
    monkeypatch.setenv("ORGANISM_BRAIN_DIR", str(tmp_path / "redirected"))
    from backend.organism.diagnostic_scheduler import DiagnosticReportStore

    store = DiagnosticReportStore()  # bare — no brain_dir argument
    resolved = Path(store._dir).resolve()
    assert str(resolved).startswith(str((tmp_path / "redirected").resolve())), (
        f"bare DiagnosticReportStore landed at {resolved}, not the redirected "
        "scratch dir — the env-aware default regressed to the literal."
    )


def test_bare_transfer_engine_lands_in_scratch(tmp_path, monkeypatch):
    monkeypatch.setenv("ORGANISM_BRAIN_DIR", str(tmp_path / "redirected"))
    from backend.organism.transfer_learning import TransferLearningEngine

    engine = TransferLearningEngine()  # bare — no brain_dir argument
    assert engine.brain_dir == (tmp_path / "redirected").resolve(), (
        f"bare TransferLearningEngine landed at {engine.brain_dir}, not the "
        "redirected scratch dir — the env-aware default regressed to the literal."
    )


def test_shadow_telemetry_path_is_isolated():
    """Third isolation hole (2026-07-29): the shadow-exit recorder path has its
    own env + literal default and was NOT covered by the brain-dir redirect —
    replay runs wrote qty>0 Jan-replay rows into the REAL telemetry file. The
    conftest now redirects the env, and live_engine derives the default from
    BRAIN_DIR; either way the import-time value must resolve outside the real
    organism_brain/."""
    from backend.organism.live_engine import ORGANISM_SHADOW_EXIT_TELEMETRY_PATH

    resolved = Path(ORGANISM_SHADOW_EXIT_TELEMETRY_PATH).resolve()
    real = (Path(__file__).resolve().parents[1] / "organism_brain").resolve()
    assert not str(resolved).startswith(str(real)), (
        f"shadow-exit telemetry path {resolved} points inside the REAL "
        "organism_brain volume — replay/test runs would pollute live telemetry "
        "(this happened 2026-07-29: 10 Jan-replay rows, quarantined)."
    )


def test_explicit_brain_dir_still_wins_over_env(tmp_path, monkeypatch):
    """An explicit argument must override the env — engine call sites pass
    brain_dir explicitly and must be unaffected by the redirect."""
    monkeypatch.setenv("ORGANISM_BRAIN_DIR", str(tmp_path / "env_dir"))
    from backend.organism.diagnostic_scheduler import DiagnosticReportStore
    from backend.organism.transfer_learning import TransferLearningEngine

    explicit = tmp_path / "explicit"
    store = DiagnosticReportStore(brain_dir=str(explicit))
    assert Path(store._dir).resolve() == (explicit / "diagnostics").resolve()
    engine = TransferLearningEngine(brain_dir=explicit)
    assert engine.brain_dir == explicit.resolve()
