# Validation Scripts Archive

These scripts were one-off validation and smoke test scripts used during development.
They have been replaced by the comprehensive testing framework in scripts/testing/.

**Archived:** 2025-10-01

## Replacement:
Use the production test suite instead:
```powershell
.\quick_validation.ps1                                    # Quick validation
.\venv\Scripts\python.exe scripts\testing\burn_in_framework.py  # Full validation
```

**Note:** These are kept for historical reference only.
