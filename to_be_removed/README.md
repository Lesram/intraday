# Codebase Cleanup - Files Moved for Review

This directory contains files that have been identified as potentially unused and moved here for verification before permanent deletion.

## Categories:
- **legacy_modules/**: Python modules not imported anywhere
- **one_off_outputs/**: Generated reports, logs, summaries not used by code
- **test_artifacts/**: Outdated tests and test result files
- **old_files/**: Files very old (2+ years) and apparently unused

## Process:
1. Files moved here are safe to test without
2. Application and tests run to verify nothing breaks
3. If tests pass, files can be permanently deleted
4. If anything fails, specific files can be restored

## Restoration:
If a file is needed, it can be moved back to its original location from the mirrored directory structure here.

**Created**: September 16, 2025
**Status**: Staging area for cleanup verification