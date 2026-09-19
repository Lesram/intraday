# Apr-8 Patch D — Script defaults to organism_brain_sandbox/

## Status: COMMITTED
- Commit SHA: `c5fb0ed`
- Base: `be2eee8`

## Source state (pre-edit)
Both scripts had `default="organism_brain"` for `--brain-dir`:
- `scripts/run_hft_organism.py:1052`
- `scripts/run_breakout_organism.py:1632`

## Diff
```
-        "--brain-dir", type=str, default="organism_brain",
-        help="Directory for brain persistence (default: organism_brain)",
+        "--brain-dir", type=str, default="organism_brain_sandbox",
+        help="Directory for brain persistence (default: organism_brain_sandbox)",
```
Applied identically to both scripts.

## Tests
- `--help` for both scripts now shows `default: organism_brain_sandbox`.
- Organism regression subset (5 files): 107 passed in 60.41s.

## Files changed
- `scripts/run_hft_organism.py`
- `scripts/run_breakout_organism.py`
