#!/usr/bin/env bash
# Dead-code removal — audit 2026-06-08.
#
# SCOPE: only the ONE removal proven safe and self-contained:
#   backend/database/repositories/  (test-only shims; production uses
#   backend.infra.repositories — 61 importers) + the 2 auto-generated
#   smoke tests that are its only consumers.
#
# Everything else flagged as "dead" by earlier passes is NOT removed here —
# it turned out to be intentional (see NOTES at bottom).
#
# This DELETES git-tracked files. Run on a branch, then VERIFY with the
# pytest commands below before committing/merging.
#
#   git checkout -b chore/remove-dead-repo-shims
#   bash scripts/remove_dead_code.sh [--dry-run]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
rm_v() { if [ "$DRY" = 1 ]; then echo "would remove: $*"; else git rm -q "$@" 2>/dev/null || rm -f "$@"; echo "removed: $*"; fi; }

echo "== Removing test-only repository shims =="
rm_v backend/database/repositories/__init__.py
rm_v backend/database/repositories/order_repository.py
rm_v backend/database/repositories/execution_repository.py
rm_v tests/unit/generated/test_auto_order_repository.py
rm_v tests/unit/generated/test_auto_execution_repository.py
# remove now-empty dir if present
rmdir backend/database/repositories 2>/dev/null || true

cat <<'EOF'

== REQUIRED verification before commit (run on your machine) ==
  ./venv/bin/python -m pytest --collect-only tests/ 2>&1 | tail -5      # must not ModuleNotFoundError
  ./venv/bin/python -m pytest tests/test_wave48_fixes.py -q             # collection-cleanliness guard
  grep -rn "database.repositories" backend tests --include='*.py' | grep -v __pycache__   # must be empty

== NOTES: candidates deliberately NOT removed (verified intentional) ==
  backend/brokers/ , backend/optimization/   -> empty __init__ kept ON PURPOSE so
      backend.brokers / backend.optimization stay importable; test_wave48_fixes.py
      ::test_z7_1 guards that pytest collection stays free of ModuleNotFoundError
      for purged submodules. Deleting reintroduces that regression.
  backend/config.py                          -> sets __path__ to act as the package
      entry; resolution vs config/__init__.py is ambiguous. Deleting risks breaking
      ALL config loading. Do not touch without running the app.
  backend/database.py                        -> deprecated & shadowed by the database/
      package, BUT the package does not clearly expose every symbol imported from it
      (e.g. get_db). Removable only after a green full-suite run confirms it. Left in.
EOF
