import sys
from pathlib import Path


def main() -> int:
    """Run a single targeted test for local debugging.

    Wrapped in a function and guarded by __main__ so importing this module
    (e.g., during pytest assertion rewriting) does not execute side effects.
    """
    try:
        import pytest  # type: ignore
    except Exception as e:
        print("Failed to import pytest:", repr(e))
        return 2

    args = [
        "-q",
        "-o",
        "addopts=",
        "--maxfail=1",
        "--disable-warnings",
        "-k",
        "test_broker_502_503_retry_pattern",
        "tests/chaos/test_broker_faults.py",
        "-s",
        "-vv",
    ]

    out_path = Path(__file__).resolve().parent / "last_test_output.txt"
    try:
        # Redirect stdout to file for reliable capture
        sys.stdout = open(out_path, "w", buffering=1, encoding="utf-8")
    except Exception:
        pass

    print("Running pytest with args:", args)
    code = pytest.main(args)
    print("pytest exit code:", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
