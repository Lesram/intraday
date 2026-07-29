# scripts/research/

Research-only scripts (post-2026-07-29 frozen-surface regime — see AGENTS.md
"FROZEN-SURFACE REGIME"). Anything here may read platform data (brain artifacts,
logs, trade history) but must NOT import from or modify the live decision path,
submit orders, or write into `organism_brain/`. New strategy ideas graduate from
here into `backend/organism/strategies/` as shadow-first modules under Rule A.
