// ═══════════════════════════════════════════════════════════════
// All Mermaid diagram definitions for the Architecture Map
// ═══════════════════════════════════════════════════════════════

// ── Tab 2: Tick Lifecycle ──────────────────────────────────────

export const governanceDecisionTree = `
flowchart TD
  START([Governance Gate]) --> HALT{Trading Halted?}
  HALT -->|Manual halt| BLOCK[entries_blocked = true]
  HALT -->|Drawdown kill active| COOLDOWN{Cooldown expired?}
  COOLDOWN -->|No| BLOCK
  COOLDOWN -->|Yes| RESUME[Auto-resume]
  HALT -->|No| FREEZE{Adaptation Frozen?}
  FREEZE -->|Yes| NOEVOLVE[Block evolution only]
  FREEZE -->|No| BUDGET{Change budget exhausted?}
  BUDGET -->|Yes| NOEVOLVE
  BUDGET -->|No| PASS([All Clear])
  BLOCK --> EXITS([Exits STILL run])
  RESUME --> PASS

  style BLOCK fill:#f5222d,color:#fff
  style PASS fill:#52c41a,color:#fff
  style EXITS fill:#faad14,color:#000
`;

export const exitDecisionTree = `
flowchart TD
  START([Exit Check]) --> P0{P0: PnL <= -8%?}
  P0 -->|Yes| SAFETY[Safety Net EXIT]
  P0 -->|No| P1{P1: Price <= Stop?}
  P1 -->|Yes| STOP[Hard Stop EXIT]
  P1 -->|No| P15{P1.5: Move >= 2R?}
  P15 -->|Yes| LOCK[Lock profit at 1R]
  P15 -->|No| P2{P2: Price >= 3R?}
  P2 -->|Yes| PARTIAL[Partial TP 30%]
  P2 -->|No| P3{P3: Full TP hit?}
  P3 -->|Yes| FULLTP[Full TP EXIT]
  P3 -->|No| P4{P4: Trail stop hit?}
  P4 -->|Yes| TRAIL[Trailing Stop EXIT]
  P4 -->|No| P4B{"P4b: Failure to follow?
  25% of max_bars, R < 0.5"}
  P4B -->|Yes| FTF[Failure-to-Follow EXIT]
  P4B -->|No| P5{P5: Time expired?}
  P5 -->|"Yes & in profit"| TIME[Time EXIT]
  P5 -->|No| P5B{"P5b: Loser time-stop?
  1.5× max_bars & PnL <= 0"}
  P5B -->|Yes| LOSER[Loser Time-Stop EXIT]
  P5B -->|No| P6[P6: Time decay tightens stop]
  P6 --> P7{P7: Stress regime?}
  P7 -->|Yes| STRESS[Tighten stop 40%]
  P7 -->|No| HOLD([No exit])

  style SAFETY fill:#f5222d,color:#fff
  style STOP fill:#f5222d,color:#fff
  style FULLTP fill:#52c41a,color:#fff
  style TRAIL fill:#faad14,color:#000
  style PARTIAL fill:#1890ff,color:#fff
  style FTF fill:#faad14,color:#000
  style LOSER fill:#f5222d,color:#fff
  style HOLD fill:#374151,color:#fff
`;

export const fillReconciliation = `
flowchart TD
  START([Fill Reconciliation]) --> CLOSED{Tracked but gone from broker?}
  CLOSED -->|Yes| GRACE{Held >= 3 ticks?}
  GRACE -->|No| SKIP1[Skip - still settling]
  GRACE -->|Yes| RECORD[Record trade + PnL]
  RECORD --> LEARN[Update learner + Kelly + calibration]
  LEARN --> CLEAN[Clean up exits + pyramids]
  CLOSED -->|No| ORPHAN{At broker but no metadata?}
  ORPHAN -->|Yes| CHECK{Has exit levels?}
  CHECK -->|Yes| SKIP2[Skip - actively managed]
  CHECK -->|No| ADOPT[Adopt: create metadata + exits]
  ORPHAN -->|No| DONE([Done])

  style RECORD fill:#52c41a,color:#fff
  style ADOPT fill:#1890ff,color:#fff
`;

// ── Tab 3: Algorithm Engine ────────────────────────────────────

export const mlSignalGeneration = `
flowchart TD
  FEAT[79 Features] --> XGB_C[XGBClassifier]
  FEAT --> XGB_R[XGBRegressor]
  XGB_C --> PUP["P(up) ∈ 0,1"]
  XGB_R --> PRED["pred_return ∈ -0.5,0.5"]

  FEAT --> ENS[Ensemble 40% blend]
  ENS --> RF[Random Forest 30%]
  ENS --> LGBM[LightGBM 25%]
  ENS --> XGB2[XGBoost 45%]
  RF --> ENSP[Ensemble P_up]
  LGBM --> ENSP
  XGB2 --> ENSP

  PUP --> BLEND["Final: 0.6×primary + 0.4×ensemble"]
  ENSP --> BLEND
  BLEND --> DIR{Direction}
  DIR -->|"P > 0.52"| BUY["+1.0 BUY"]
  DIR -->|"P < 0.48"| SELL["-1.0 SELL"]
  DIR -->|"0.48-0.52"| HOLD["0.0 HOLD"]

  style BUY fill:#52c41a,color:#fff
  style SELL fill:#f5222d,color:#fff
  style HOLD fill:#374151,color:#fff
`;

export const alphaScanner = `
flowchart TD
  INPUT[Symbol Features] --> ML["ML Score (0.25)"]
  INPUT --> BRK["Breakout (0.20)"]
  INPUT --> INST["Institutional (0.15)"]
  INPUT --> MOM["Momentum (0.15)"]
  INPUT --> MOMQ["Mom Quality (0.10)"]
  INPUT --> VOL["Volume (0.10)"]
  INPUT --> REG["Regime Align (0.05)"]

  ML --> COMP[Composite Score]
  BRK --> COMP
  INST --> COMP
  MOM --> COMP
  MOMQ --> COMP
  VOL --> COMP
  REG --> COMP

  COMP --> MOD{Modifiers}
  MOD --> HOLD_PEN["ML Hold → ×0.30"]
  MOD --> FIT["Fitness → ×(0.5+f)"]

  FIT --> GATE{"Composite >= 0.15?"}
  GATE -->|Yes| TOP5[Top 3 Candidates]
  GATE -->|No| REJECT[Rejected]

  style TOP5 fill:#52c41a,color:#fff
  style REJECT fill:#f5222d,color:#fff
`;

export const breakoutScanner = `
flowchart TD
  INPUT[Symbol Data] --> SQ["Squeeze (0.25)"]
  INPUT --> VS["Volume Surge (0.25)"]
  INPUT --> RC["Range Contraction (0.15)"]
  INPUT --> RS["Relative Strength (0.15)"]
  INPUT --> PB["Pivot Breakout (0.15)"]
  INPUT --> IF["Institutional Flow (0.05)"]

  SQ --> COMP[Composite Score]
  VS --> COMP
  RC --> COMP
  RS --> COMP
  PB --> COMP
  IF --> COMP

  COMP --> BONUS{Squeeze + Volume fired?}
  BONUS -->|Yes| BOOST["×1.30 bonus"]
  BONUS -->|No| RAW[Raw score]
  BOOST --> FILTER{"Composite >= 0.20?"}
  RAW --> FILTER
  FILTER -->|Yes| TOP8[Top N Signals]
  FILTER -->|No| DROP[Dropped]

  style TOP8 fill:#52c41a,color:#fff
  TOP8 -.->|"N = MAX_OPEN_POSITIONS (15)"| NOTE[ ]
  style NOTE fill:none,stroke:none
  style DROP fill:#f5222d,color:#fff
`;

export const kellySizer = `
flowchart TD
  START([Kelly Pipeline]) --> RAW[Step 1: Raw Kelly]
  RAW --> HALF[Step 2: Half-Kelly × 0.5]
  HALF --> DD[Step 3: Drawdown Scale]
  DD --> VOL[Step 4: Vol Target 0.15/vol]
  VOL --> REG[Step 5: Regime Scale]
  REG --> CONF[Step 6: Confidence Scale]
  CONF --> BRK[Step 7: Breakout Bonus]
  BRK --> COMBINE["target = half × dd × vol × regime × conf × brk"]
  COMBINE --> CAP{Caps & Filters}
  CAP --> MAX10["Per-position: 10%"]
  CAP --> PORT95["Portfolio: 95%"]
  CAP --> MIN["Min: $2,000 / 0.1% / 1 share"]
  MAX10 --> SHARES["shares = equity × weight / price"]
  PORT95 --> SHARES
  MIN --> SHARES

  style COMBINE fill:#1890ff,color:#fff
`;

export const adaptiveExitCascade = `
flowchart TD
  ENTRY[Entry Price + ATR] --> LEVELS[Create Exit Levels]
  LEVELS --> STOP["stop = entry - ATR×stop_mult"]
  LEVELS --> TP["tp = entry + risk×tp_r_mult"]
  LEVELS --> TRAIL["trail_activation = entry + ATR×3.0"]
  LEVELS --> PTP["partial_tp = entry + risk×3.0R"]

  subgraph Regime Parameters
    TU["trending_up: stop=2.0 tp=6.0R trail=3.5"]
    TD2["trending_down: stop=1.3 tp=3.0R trail=2.0"]
    CH["chop: stop=1.2 tp=2.5R trail=1.5"]
    HV["high_vol: stop=2.0 tp=3.0R trail=2.5"]
    LV["low_vol: stop=1.8 tp=5.0R trail=3.0"]
    ST["stress: stop=1.2 tp=2.0R trail=1.5"]
  end

  style TU fill:#52c41a,color:#fff
  style ST fill:#f5222d,color:#fff
  style HV fill:#faad14,color:#000
`;

export const regimeDetection = `
flowchart LR
  DATA[Raw Data] --> S1[Trend Slope]
  DATA --> S2[Price vs SMA]
  DATA --> S3[ATR Volatility]
  DATA --> S4[Returns Vol]
  DATA --> S5[Volume Anomaly]

  S1 --> SCORES[Raw Scores]
  S2 --> SCORES
  S3 --> SCORES
  S4 --> SCORES
  S5 --> SCORES

  SCORES --> SOFTMAX[Softmax]
  SOFTMAX --> EMA["EMA Smoothing α=0.3"]
  EMA --> PRIORITY{"3-Tier Priority"}
  PRIORITY -->|"1. Cross-Asset"| CA[Sector ETF Breadth]
  PRIORITY -->|"2. SPY-Based"| SPY[SPY Features]
  PRIORITY -->|"3. Aggregate"| AGG[All Symbols Avg]
  CA --> ARGMAX[argmax]
  SPY --> ARGMAX
  AGG --> ARGMAX
  ARGMAX --> LABEL{Regime Label}

  LABEL --> TU[trending_up]
  LABEL --> TD2[trending_down]
  LABEL --> CH[chop]
  LABEL --> HV[high_vol]
  LABEL --> LV[low_vol]
  LABEL --> ST[stress]
  LABEL --> UN[unknown]

  style TU fill:#52c41a,color:#fff
  style ST fill:#f5222d,color:#fff
  style HV fill:#faad14,color:#000
  style CH fill:#722ed1,color:#fff
`;

export const selfEvolution = `
flowchart TD
  START(["Evolution Loop (>= 8 trades)"]) --> S1[1. Signal Weight Adaptation]
  S1 --> S2[2. Exit Parameter Tuning]
  S2 --> S3[3. Regime-Size Scaling]
  S3 --> S4[4. Feature Selection/Weighting]
  S4 --> S5[5. Symbol Fitness]
  S5 --> S6[6. Direction Threshold Calibration]
  S6 --> S7[7. Breakout Weight Adaptation]
  S7 --> S8[8. Breakout Period Adaptation]
  S8 --> S9[9. Short-Side Resurrection]
  S9 --> S10[10. XGBoost Hyperparameter Evolution]
  S10 --> VALIDATE{Walk-forward gate}
  VALIDATE -->|Pass| APPLY[Apply evolved params]
  VALIDATE -->|Fail| ROLLBACK[Keep old params]

  style APPLY fill:#52c41a,color:#fff
  style ROLLBACK fill:#f5222d,color:#fff
`;

// ── Tab 4: Infrastructure ──────────────────────────────────────

export const orderExecutionSequence = `
sequenceDiagram
  participant LE as LiveEngine
  participant OS as OrderService
  participant OB as Outbox
  participant GR as Guardrails
  participant AL as Alpaca REST
  participant WS as WebSocket Stream
  participant DB as Database
  participant FE as Frontend

  LE->>OS: place_order(symbol, qty, side)
  OS->>GR: validate(order)
  GR-->>OS: pass/reject
  OS->>DB: INSERT order (pending)
  OS->>OB: INSERT outbox event
  OB->>AL: POST /v2/orders
  AL-->>OB: order_id
  OB->>DB: UPDATE order (submitted)
  WS-->>DB: fill event → UPDATE order (filled)
  WS-->>FE: Socket.IO push
`;

export const outboxDLQ = `
flowchart TD
  EVENT[Outbox Event] --> DISPATCH{Dispatcher picks up}
  DISPATCH --> SEND[Send to Alpaca]
  SEND --> OK{Success?}
  OK -->|Yes| MARK[Mark dispatched]
  OK -->|No| RETRY{Attempts < 5?}
  RETRY -->|Yes| BACKOFF["Backoff: 2^attempt × 1s"]
  BACKOFF --> SEND
  RETRY -->|No| DLQ[Move to DLQ]
  DLQ --> ALERT[Alert: order stuck]
  DLQ --> MANUAL["Manual intervention required"]

  style MARK fill:#52c41a,color:#fff
  style DLQ fill:#f5222d,color:#fff
  style ALERT fill:#faad14,color:#000
`;

export const orderGuardrails = `
flowchart TD
  ORDER[Incoming Order] --> G1{G1: Duplicate check}
  G1 -->|Dup| REJECT1[REJECT]
  G1 -->|OK| G2{G2: Position limit 15}
  G2 -->|Over| REJECT2[REJECT]
  G2 -->|OK| G3{G3: Sector limit 4}
  G3 -->|Over| REJECT3[REJECT]
  G3 -->|OK| G4{G4: Notional min $2K}
  G4 -->|Under| REJECT4[REJECT]
  G4 -->|OK| G5{G5: Portfolio 95% cap}
  G5 -->|Over| REJECT5[REJECT]
  G5 -->|OK| G6{G6: Rate limit}
  G6 -->|Hit| REJECT6[REJECT]
  G6 -->|OK| G7{G7: Drawdown gate}
  G7 -->|Killed| REJECT7[REJECT]
  G7 -->|OK| G8{G8: LONG_ONLY check}
  G8 -->|Short blocked| REJECT8[REJECT]
  G8 -->|OK| PASS([Order Approved])

  style PASS fill:#52c41a,color:#fff
  style REJECT1 fill:#f5222d,color:#fff
  style REJECT2 fill:#f5222d,color:#fff
  style REJECT3 fill:#f5222d,color:#fff
  style REJECT4 fill:#f5222d,color:#fff
  style REJECT5 fill:#f5222d,color:#fff
  style REJECT6 fill:#f5222d,color:#fff
  style REJECT7 fill:#f5222d,color:#fff
  style REJECT8 fill:#f5222d,color:#fff
`;

export const circuitBreaker = `
stateDiagram-v2
  [*] --> CLOSED
  CLOSED --> OPEN : Failure threshold reached
  OPEN --> HALF_OPEN : Recovery timeout expires
  HALF_OPEN --> CLOSED : Probe succeeds
  HALF_OPEN --> OPEN : Probe fails

  CLOSED : Normal operation
  CLOSED : Failures counted
  OPEN : All calls fail-fast
  OPEN : No requests to broker
  HALF_OPEN : Single probe request
  HALF_OPEN : Testing if recovered
`;

// ── Tab 5: ML Pipeline ────────────────────────────────────────

export const mlPipeline = `
flowchart TD
  S1[1. Data Ingestion] --> S2[2. Feature Engineering]
  S2 --> S3[3. Feature Selection]
  S3 --> S4[4. Train/Val Split 80/20]
  S4 --> S5[5. Model Training]
  S5 --> S6[6. Walk-Forward Evaluation]
  S6 --> S7{7. Validation Gate}
  S7 -->|Pass| S8[8. Promotion]
  S7 -->|Fail| REJECT[Reject - keep old model]

  S5 --> XGB[XGBoost]
  S5 --> RF[Random Forest]
  S5 --> LGBM[LightGBM]
  XGB --> ENSEMBLE[Ensemble Blend]
  RF --> ENSEMBLE
  LGBM --> ENSEMBLE
  ENSEMBLE --> S6

  style S8 fill:#52c41a,color:#fff
  style REJECT fill:#f5222d,color:#fff
`;

export const trainingOrchestrator = `
flowchart TD
  TRIGGER["Trigger: every RETRAIN_INTERVAL ticks"] --> BG{Background available?}
  BG -->|Yes| PROC[ProcessPoolExecutor]
  BG -->|No| SYNC[Synchronous path]
  PROC --> TRAIN[Train ML + evolve params]
  SYNC --> TRAIN
  TRAIN --> VALID{Composite score check}
  VALID -->|"score > 0.25 (new)"| ACCEPT[Accept model]
  VALID -->|"improve >= 5% (existing)"| ACCEPT
  VALID -->|Fail| KEEP[Keep old model]
  ACCEPT --> SWAP[Atomic swap: weights + params]
  PROC --> STUCK{"Running > 30 ticks?"}
  STUCK -->|Yes| RESET[Force reset → sync fallback]

  style ACCEPT fill:#52c41a,color:#fff
  style KEEP fill:#faad14,color:#000
  style RESET fill:#f5222d,color:#fff
`;

export const driftDetection = `
flowchart TD
  FEATURES[Live Feature Distributions] --> PSI[PSI Calculation]
  PSI --> CHECK{"PSI > threshold?"}
  CHECK -->|Yes| DRIFT[Drift Detected]
  DRIFT --> RETRAIN[Trigger Early Retrain]
  DRIFT --> ALERT[Alert: feature drift]
  CHECK -->|No| OK[Features stable]

  FEATURES --> CHURN[Regime Churn Rate]
  CHURN --> CHURN_CHECK{"churn > threshold?"}
  CHURN_CHECK -->|Yes| UNSTABLE[Regime unstable]
  CHURN_CHECK -->|No| STABLE[Regime stable]

  style DRIFT fill:#faad14,color:#000
  style OK fill:#52c41a,color:#fff
`;

// ── Tab 6: Operations ──────────────────────────────────────────

export const engineStartup = `
sequenceDiagram
  participant APP as FastAPI App
  participant SCH as OrganismScheduler
  participant ENG as LiveEngine
  participant BRAIN as Brain Files
  participant BRK as Alpaca Broker
  participant DB as Database
  participant STREAM as StreamingProvider

  APP->>SCH: startup event
  SCH->>ENG: create OrganismLiveEngine
  ENG->>BRAIN: load brain state (JSON + CSV)
  BRAIN-->>ENG: models, params, exits, kelly stats
  ENG->>BRK: verify connection + account
  BRK-->>ENG: account info
  ENG->>DB: init session factory
  ENG->>STREAM: start market data stream
  STREAM->>BRK: subscribe to bar updates
  ENG->>ENG: reconstruct position state
  ENG->>ENG: compute initial features
  SCH->>SCH: schedule tick every 10s
  SCH->>SCH: schedule diagnostics (pre-open/post-close)
  Note over SCH,ENG: Engine is now live
`;

// ── New: State-Dependent Cost Model ─────────────────────────

export const stateDependentCost = `
flowchart TD
  QUOTE["Real-Time Quote (bid/ask)"] --> BASE["base_spread = (ask-bid)/mid"]
  NOQUOTE["No Quote Available"] --> FALLBACK["Fallback: 10bps"]
  BASE --> MULT["Apply Multipliers"]
  FALLBACK --> MULT

  MULT --> TIME["time_mult (time of day)"]
  MULT --> LIQ["liquidity_mult (volume ratio)"]

  TIME --> CALC["spread_cost = base × time × liquidity"]
  LIQ --> CALC

  CALC --> CLAMP["Clamp to [3bps, 50bps]"]
  CLAMP --> GATE{"predicted_return >= cost × 2?"}
  GATE -->|Yes| PASS([Edge Clears Cost])
  GATE -->|No| BLOCK([Skip — Insufficient Edge])

  subgraph Time Multipliers
    T1["Pre-market: 2.0×"]
    T2["Open (9:30-9:45): 1.5×"]
    T3["Morning: 0.9×"]
    T4["Midday: 1.0×"]
    T5["Afternoon: 0.95×"]
    T6["Close (3:45-4:00): 1.3×"]
    T7["After-hours: 2.5×"]
  end

  style PASS fill:#52c41a,color:#fff
  style BLOCK fill:#f5222d,color:#fff
  style CLAMP fill:#1890ff,color:#fff
`;

// ── New: Entry Scanning Pipeline ─────────────────────────────

export const entryScanningPipeline = `
flowchart TD
  START([Phase 7: Entry Scan]) --> BRK["7a: Breakout Scan
  6 detectors → Top N signals"]
  BRK --> ML["7b: ML Predictions
  Batch predict all symbols"]
  ML --> ALPHA["7c: Alpha Scan
  7-factor composite → Top 3"]
  ALPHA --> GATES["7d: Filter (8 Gates)"]

  GATES --> G1{Already have position?}
  G1 -->|No| G2{In exit cooldown?}
  G2 -->|No| G3{Pending entry order?}
  G3 -->|No| G4{In entry_metadata?}
  G4 -->|No| G5{LONG_ONLY + short?}
  G5 -->|No| G6{Sector gate 4/sector?}
  G6 -->|No| G7{Fitness < 0.45?}
  G7 -->|No| G8{Liquidity < 10K vol?}

  G1 -->|Yes| REJ[REJECT]
  G2 -->|Yes| REJ
  G3 -->|Yes| REJ
  G4 -->|Yes| REJ
  G5 -->|Yes| REJ
  G6 -->|Yes| REJ
  G7 -->|Yes| REJ
  G8 -->|Yes| REJ

  G8 -->|No| CONF["Blended Confidence
  0.50×ML + 0.30×breakout + 0.20×tension"]

  CONF --> PURE["7e: Pure Breakout Additions
  Max 2/tick, score >= 0.55"]

  PURE --> SORT["7f: Sort by score×confidence
  Truncate to available slots"]

  style START fill:#1890ff,color:#fff
  style REJ fill:#f5222d,color:#fff
  style SORT fill:#52c41a,color:#fff
  style CONF fill:#faad14,color:#000
`;
