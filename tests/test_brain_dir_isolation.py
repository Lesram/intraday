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
