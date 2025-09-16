# STANDARDIZED PLATFORM CONFIGURATION
*No more directory confusion - Fixed settings*

## 🏠 PLATFORM ROOT (NEVER CHANGES)
```
C:\Users\Marsel\intra\algotrading_platform
```

## 📁 DIRECTORY STRUCTURE
```
C:\Users\Marsel\intra\algotrading_platform\
├── tests/                          # All 3,907 test files
├── backend/                        # Platform code
├── scripts/                        # Utility scripts
├── full_test_results.xml          # Test results (generated)
├── standardized_test_runner.py     # Standard test execution
└── comprehensive_analyzer.py       # Standard analysis
```

## 🔧 STANDARDIZED COMMANDS

### Test Execution (USE ONLY THIS)
```bash
# Navigate to platform root
cd "C:\Users\Marsel\intra\algotrading_platform"

# Run standardized test suite
python standardized_test_runner.py
```

### Analysis (AFTER TESTS COMPLETE)
```bash
# From platform root
python comprehensive_analyzer.py
```

## 🚫 DEPRECATED APPROACHES (DO NOT USE)
- Manual directory navigation in terminals
- Multiple variations of pytest commands
- Different XML output files
- Ad-hoc monitoring scripts

## ✅ STANDARDIZED BENEFITS
1. **Fixed Working Directory**: Always `C:\Users\Marsel\intra\algotrading_platform`
2. **Single Test Command**: `python standardized_test_runner.py`
3. **Consistent Output**: Always `full_test_results.xml`
4. **No Directory Confusion**: Built-in directory enforcement
5. **Repeatable Process**: Same approach every time

## 🎯 USAGE PROTOCOL
1. **ALWAYS** start from: `C:\Users\Marsel\intra\algotrading_platform`
2. **ALWAYS** use: `python standardized_test_runner.py`
3. **ALWAYS** check: `full_test_results.xml` exists
4. **ALWAYS** analyze: `python comprehensive_analyzer.py`

---

*This eliminates all directory confusion and standardizes our test execution approach.*
