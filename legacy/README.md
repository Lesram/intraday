# Legacy Code Archive

This folder contains deprecated and superseded code files that have been moved here to prevent accidental imports while preserving history.

## Files

### Configuration Files
- **config_old.py** - Original configuration using python-decouple (deprecated)
- **config_broken.py** - Broken configuration version (reference only)
- **config_new.py** - Intermediate configuration version (superseded)
- **config_v2.py** - Second iteration configuration (superseded)

**Current Configuration**: Use `backend/config.py` - Pydantic V2 settings with nested sections

### API Files
- **main_old.py** - Original main.py before factory pattern migration (deprecated)

**Current API**: Use `backend/api/main.py` with `backend/api/factory.py` create_app pattern

### Risk Management
- **risk_manager_backup.py** - Backup of risk manager during refactoring (reference only)

**Current Risk Manager**: Use `backend/risk/risk_manager.py`

## ⚠️ Important Notes

1. **Do NOT import from this folder** - These files are archived for reference only
2. **Do NOT modify these files** - They are frozen snapshots
3. **For new features** - Always use the current modules in `backend/`
4. **For bug fixes** - Work on the current codebase, not legacy files

## Migration History

- **2025-08**: Consolidated configuration to single `backend/config.py`
- **2025-08**: Migrated main.py to factory pattern with create_app
- **2025-08**: Finalized risk manager with async-first design

## Safe Deletion

These files can be safely deleted after:
1. All references are confirmed removed from codebase
2. No active branches depend on them
3. History is preserved in git commits
