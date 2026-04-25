# Organism Feature Status

| Feature | Status | Evidence |
|---|---|---|
| ML signal generation | ✅ ACTIVE | XGBoost runs every tick, predicts direction + magnitude |
| Confidence calibration | ✅ ACTIVE | 293 trades of calibration data, bin-based correction |
| Effective confidence | ✅ ACTIVE | Used in production mode for entry gating |
| Background ML training | ✅ ACTIVE | Retrains every ~180 bars via ProcessPoolExecutor |
| Model acceptance gate | ✅ ACTIVE | acceptance_gate validates new models before applying |
| Alpha scanning | ✅ ACTIVE | Composite scoring every tick |
| Breakout scanning | ✅ ACTIVE | BB/ATR/volume scoring every tick |
| Regime detection | ✅ ACTIVE | Cross-asset regime detection every tick |
| Adaptive exits | ✅ ACTIVE | Full priority chain (SL/TP/FTF/trailing/timeout) |
| Pyramiding | ✅ ACTIVE | Layer add/cut logic with Exp1A gate |
| Kelly sizing | ✅ ACTIVE | Vol-target sizing with regime scaling |
| Brain persistence | ✅ ACTIVE | 787 saves, Full Patch F, force-save available |
| Universe rotation | ✅ ACTIVE | Dynamic symbol management |
| Sector gating | ✅ ACTIVE | Per-sector position limits |
| Governance controls | ✅ ACTIVE | Halt/freeze/resume + drawdown checks |
| Parameter evolution | ⏳ FROZEN (293/300) | Unfreezes in ~7 trades |
| Transfer learning warm-start | ⏳ FROZEN (293/300) | Applied at init, locked behind same freeze |
| Nightly retraining | ❌ DISABLED | ORGANISM_NIGHTLY_ENABLED not in .env |
| Promotion pipeline | ❌ DORMANT | Only fires after nightly training |
| Walk-forward validation | ❌ OFFLINE ONLY | Not used in live gating |
| Ensemble models | ⚠️ OPTIONAL | Soft fallback, not critical path |
| Exploration queue | ❌ DEAD CODE | Routes to queue nobody reads |
