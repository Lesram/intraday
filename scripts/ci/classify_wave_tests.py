"""V12 W70: classify wave-fix regression tests as marker-only / behavioral / mixed.

A *marker-only* test is one whose only assertions are source-grep style
(``assert "X" in inspect.getsource(...)``,
 ``assert "X" in open(...).read()``,
 ``assert os.path.isfile(...)``).  These give false comfort: the
production code can break while the test still passes (V11 AA5-1 JWT
regression was the canonical example: the test grepped for
``"leeway=JWT_CLOCK_SKEW"`` in the source while the kwarg was being
swallowed by ``except Exception`` at runtime).

A *behavioral* test is one that calls user code, mints state, hits an
endpoint, instantiates the SUT, etc., and asserts on its return value
or observable side-effect.

A *mixed* test does both — typically a behavioral assertion plus a
secondary marker check.

Output: JSON to stdout with per-test classification + per-file rollup +
overall summary.  Exit code 0 always (informational); the
``forbid_marker_only_critical_high.py`` script (W73) is the gating one.

Usage:
    python scripts/ci/classify_wave_tests.py [--root tests] [--json out.json]
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Names whose calls are inspection-only (marker style — they don't
# exercise the SUT, they only verify it exists / contains a string).
_MARKER_CALL_NAMES: frozenset[str] = frozenset({
    "getsource",          # inspect.getsource
    "getsourcefile",
    "getmodule",
    "getmembers",
    "isfile",             # os.path.isfile
    "exists",             # os.path.exists
    "isdir",
    "read_text",          # pathlib.Path.read_text
    "read",               # open(...).read()
    # Attribute-existence checks: pure structural, not behavioral.
    "hasattr",
    # ``dir(obj)`` returns the attribute list — inspection only.
    "dir",
})

# Stdlib / inspection roots — calls to attributes of these are NOT user-code.
_STDLIB_ROOTS: frozenset[str] = frozenset({
    "inspect", "os", "sys", "ast", "re", "json", "pathlib",
    "datetime", "time", "math", "uuid", "typing", "abc",
    "collections", "functools", "itertools", "logging",
    "subprocess",  # subprocess.run is borderline; counted as behavioral when
                   # the called script IS the SUT.  The default classifier
                   # treats subprocess.run() as behavioral (rare to use it
                   # for pure marker checks).
})

# Builtins that don't count as behavioral on their own.
_TRIVIAL_BUILTINS: frozenset[str] = frozenset({
    "len", "str", "int", "float", "bool", "list", "dict", "tuple", "set",
    "frozenset", "range", "enumerate", "zip", "iter", "next", "isinstance",
    "issubclass", "type", "id", "hash", "repr", "print", "open", "any", "all",
    "min", "max", "sum", "sorted", "reversed", "map", "filter", "abs", "round",
    "getattr", "setattr", "hasattr", "delattr", "vars",
})


@dataclass
class TestClassification:
    file: str
    name: str
    line: int
    classification: str   # "marker-only" | "behavioral" | "mixed"
    marker_assertions: int
    behavioral_signals: int
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "name": self.name,
            "line": self.line,
            "classification": self.classification,
            "marker_assertions": self.marker_assertions,
            "behavioral_signals": self.behavioral_signals,
            "notes": self.notes,
        }


def _qualified_attr_name(node: ast.AST) -> str | None:
    """Return ``a.b.c`` form for ast.Attribute / ast.Name; else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _qualified_attr_name(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def _expr_references_marker(expr: ast.AST, marker_vars: set[str]) -> bool:
    """True iff this expression syntactically depends on a marker source —
    a ``getsource()``/``read()``/``isfile()`` call OR a name already bound
    to such a value, OR ``.count(...)``/``.find(...)``/etc. on one."""
    for sub in ast.walk(expr):
        if isinstance(sub, ast.Call) and _is_marker_call(sub):
            return True
        if isinstance(sub, ast.Name) and sub.id in marker_vars:
            return True
    return False


def _collect_source_grep_vars(func: ast.FunctionDef) -> set[str]:
    """Find local names whose value is *derived* from a marker source.

    Direct: ``src = inspect.getsource(mod)``, ``src = open(p).read()``.
    Transitive: ``n = src.count("Depends(require_admin)")``,
                ``txt = src.replace("a", "b")``, etc.

    A name in this set means an ``assert ... <name> ...`` is
    syntactically a source-grep, not a runtime probe.
    """
    bound: set[str] = set()
    # Iterate Assign nodes in source order; transitive marker propagation
    # depends on prior assignments having been seen.
    for node in ast.iter_child_nodes(func):
        # Walk the whole subtree but only react on assigns at any depth.
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Assign):
                continue
            value = sub.value
            # Direct marker call: src = inspect.getsource(mod)
            if isinstance(value, ast.Call) and _is_marker_call(value):
                for target in sub.targets:
                    if isinstance(target, ast.Name):
                        bound.add(target.id)
                continue
            # ``open(...).read()`` chain.
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
                if value.func.attr == "read" and isinstance(value.func.value, ast.Call):
                    inner = value.func.value
                    if isinstance(inner.func, ast.Name) and inner.func.id == "open":
                        for target in sub.targets:
                            if isinstance(target, ast.Name):
                                bound.add(target.id)
                        continue
            # Transitive: any expression that references a marker var or
            # marker call (e.g. n = src.count("X"), txt = src + "more").
            if _expr_references_marker(value, bound):
                for target in sub.targets:
                    if isinstance(target, ast.Name):
                        bound.add(target.id)
    return bound


def _is_marker_call(call: ast.Call) -> bool:
    """True iff this Call is purely an inspection (no user-code execution)."""
    if isinstance(call.func, ast.Attribute):
        if call.func.attr in _MARKER_CALL_NAMES:
            return True
    if isinstance(call.func, ast.Name) and call.func.id in _MARKER_CALL_NAMES:
        return True
    return False


def _is_userland_call(call: ast.Call, marker_vars: set[str]) -> bool:
    """True iff this Call exercises user code (not a marker / trivial builtin)."""
    if _is_marker_call(call):
        return False
    qual = _qualified_attr_name(call.func)
    if qual is None:
        # E.g. dynamic call on a subscription or attribute chain — treat as user code.
        return True
    head = qual.split(".", 1)[0]
    if head in _STDLIB_ROOTS:
        # subprocess.run is the one borderline case; we still count it because
        # the typical wave-test use is ``subprocess.run(["./venv/bin/python", "scripts/ci/...py"])``
        # which IS exercising user code (the script).
        if head == "subprocess":
            return True
        return False
    if head in _TRIVIAL_BUILTINS:
        return False
    if head in marker_vars:
        return False
    # Importlib reload is a special case: counted as behavioral if it's
    # followed by inspection of the reloaded module's runtime state.  We
    # under-count by treating it as behavioral.
    return True


def _classify_assertion(test: ast.expr, marker_vars: set[str]) -> str:
    """Classify a single ``assert <test>`` expression.

    Returns "marker" if it's a source-grep style assertion,
    "behavioral" if it asserts on runtime state / return values,
    "structural" if it's e.g. a file-existence check (counted as marker
    for the marker-only classification, but flagged separately).
    """
    # ``assert <a> and <b>`` / ``assert <a> or <b>`` — recurse on operands.
    # Conservative rule: if any operand is behavioral, the assertion is
    # behavioral; if all operands are marker, it's marker; otherwise marker
    # (structural/marker beats nothing).
    if isinstance(test, ast.BoolOp):
        kinds = {_classify_assertion(v, marker_vars) for v in test.values}
        if "behavioral" in kinds:
            return "behavioral"
        if "marker" in kinds:
            return "marker"
        if "structural" in kinds:
            return "structural"
        return "behavioral"
    # ``assert "X" in src`` / ``assert "X" not in src`` — source-grep.
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        op = test.ops[0]
        if isinstance(op, (ast.In, ast.NotIn)):
            left = test.left
            right = test.comparators[0]
            left_is_string = isinstance(left, ast.Constant) and isinstance(left.value, str)
            right_is_marker = (
                (isinstance(right, ast.Name) and right.id in marker_vars)
                or (isinstance(right, ast.Call) and _is_marker_call(right))
                or _expr_references_marker(right, marker_vars)
            )
            if left_is_string and right_is_marker:
                return "marker"
        # ``assert n >= 6`` / ``assert count == 3`` where the LHS was
        # derived from a marker source (e.g. ``src.count("X")``).
        if isinstance(test.left, ast.Name) and test.left.id in marker_vars:
            return "marker"
        if _expr_references_marker(test.left, marker_vars):
            # LHS references getsource/read/etc. directly without the
            # intermediate variable — still source-grep.
            return "marker"
    # ``assert os.path.isfile(...)``
    if isinstance(test, ast.Call) and _is_marker_call(test):
        return "marker"
    # ``assert <call>(...) ...``  — any user-land call → behavioral.
    if isinstance(test, ast.Call):
        if _is_userland_call(test, marker_vars):
            return "behavioral"
    if isinstance(test, ast.Compare):
        # ``assert response.status_code == 200`` etc.
        for sub in ast.walk(test):
            if isinstance(sub, ast.Call) and _is_userland_call(sub, marker_vars):
                return "behavioral"
        # No call but compares to attribute / name — likely behavioral on bound state.
        return "behavioral"
    if isinstance(test, ast.Attribute):
        return "behavioral"
    if isinstance(test, ast.Name):
        if test.id in marker_vars:
            return "marker"
        return "behavioral"
    if isinstance(test, ast.Constant):
        # ``assert True`` — irrelevant; classify as structural.
        return "structural"
    return "behavioral"


def classify_test(file: str, func: ast.FunctionDef) -> TestClassification:
    marker_vars = _collect_source_grep_vars(func)
    marker_count = 0
    behavioral_count = 0
    notes: list[str] = []

    # Walk all top-level statements (including nested in try/with/for).
    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            kind = _classify_assertion(node.test, marker_vars)
            if kind == "marker":
                marker_count += 1
            elif kind == "behavioral":
                behavioral_count += 1
        elif isinstance(node, ast.Call):
            # User-land call (not in an assert, but exercising code).
            # Skip if the call is the immediate child of an Assign whose
            # target ends up as a marker-var (we already counted that).
            if _is_userland_call(node, marker_vars):
                # Heuristic: count if the call appears to mint state or invoke SUT.
                # We do NOT double-count the same assert's call.
                # Because ast.walk yields nested nodes, an Assert containing a
                # Call would already have classified that assert as behavioral.
                # We add an extra signal only for free-standing calls (e.g.
                # ``learner.record_trade(...)``).
                # Skip if this call is reachable from any Assert.test we've seen —
                # over-counting is acceptable for the classifier (marker-only is
                # the conservative bucket).
                behavioral_count += 1

    if marker_count > 0 and behavioral_count == 0:
        cls = "marker-only"
    elif behavioral_count > 0 and marker_count == 0:
        cls = "behavioral"
    elif behavioral_count > 0 and marker_count > 0:
        cls = "mixed"
    else:
        # No assertions and no user-land calls → degenerate; classify as structural.
        cls = "structural"
        notes.append("no_assertions_or_calls")

    return TestClassification(
        file=file,
        name=func.name,
        line=func.lineno,
        classification=cls,
        marker_assertions=marker_count,
        behavioral_signals=behavioral_count,
        notes=notes,
    )


def classify_file(path: Path) -> list[TestClassification]:
    src = path.read_text()
    tree = ast.parse(src, filename=str(path))
    out: list[TestClassification] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            out.append(classify_test(str(path), node))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="tests", help="tests directory root")
    parser.add_argument(
        "--pattern", default="test_wave*_fixes.py",
        help="glob for wave-fix test files",
    )
    parser.add_argument(
        "--full-corpus", action="store_true",
        help=(
            "V13 W97: scan all wave-style test files: test_wave*_fixes.py, "
            "test_v??_w*.py, test_v??_wave*.py.  Replaces --pattern."
        ),
    )
    parser.add_argument(
        "--json", default="-",
        help="output path (- for stdout)",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if args.full_corpus:
        # V13 W97: aggregate all wave-style file conventions.
        patterns = (
            "test_wave*_fixes.py",
            "test_v[0-9][0-9]_w*.py",
            "test_v[0-9][0-9]_wave*.py",
        )
        seen: set[Path] = set()
        files = []
        for pat in patterns:
            for f in root.glob(pat):
                if f not in seen:
                    seen.add(f)
                    files.append(f)
        files.sort()
    else:
        files = sorted(root.glob(args.pattern))
    rows: list[TestClassification] = []
    for f in files:
        rows.extend(classify_file(f))

    counts: dict[str, int] = {}
    by_file: dict[str, dict[str, int]] = {}
    for r in rows:
        counts[r.classification] = counts.get(r.classification, 0) + 1
        fb = by_file.setdefault(r.file, {})
        fb[r.classification] = fb.get(r.classification, 0) + 1

    total = len(rows)
    pct_marker_only = (counts.get("marker-only", 0) / total * 100) if total else 0
    summary = {
        "files_scanned": len(files),
        "tests_total": total,
        "by_classification": counts,
        "pct_marker_only": round(pct_marker_only, 2),
        "by_file": by_file,
        "tests": [r.as_dict() for r in rows],
    }

    text = json.dumps(summary, indent=2, sort_keys=True)
    if args.json == "-":
        print(text)
    else:
        Path(args.json).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
