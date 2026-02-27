import { Typography } from 'antd';
import MermaidDiagram from '../components/MermaidDiagram';
import CollapsibleSection from '../components/CollapsibleSection';
import FormulaBlock from '../components/FormulaBlock';
import ThresholdTable from '../components/ThresholdTable';
import {
  mlSignalGeneration, alphaScanner, breakoutScanner,
  kellySizer, adaptiveExitCascade, regimeDetection, selfEvolution,
} from '../data/mermaidDefinitions';
import { exitRegimeParams, regimeScales } from '../data/thresholds';

const { Title } = Typography;

const AlgorithmEngineTab = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <Title level={4} style={{ margin: 0 }}>Algorithm Engine Deep Dives</Title>

    <CollapsibleSection title="ML Signal Generation" subtitle="Dual XGB → ensemble → blend → direction" defaultOpen>
      <MermaidDiagram definition={mlSignalGeneration} />
      <FormulaBlock
        label="Confidence Calibration"
        formula={`raw_confidence = abs(p_up - 0.5) × 2     → [0, 1]
bin_idx = int(raw_confidence × 5)          → 5 bins
multiplier = actual_accuracy / bin_midpoint → capped at 2.0
calibrated = raw_confidence × multiplier   → capped at 1.0`}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Alpha Scanner" subtitle="7-factor weighted composite score">
      <MermaidDiagram definition={alphaScanner} />
      <FormulaBlock
        label="7-Factor Composite Formula"
        formula={`COMPOSITE = 0.25 × ml_score
          + 0.20 × breakout_score
          + 0.15 × institutional_score
          + 0.15 × momentum_score (cross-sectional rank)
          + 0.10 × momentum_quality
          + 0.10 × volume_score
          + 0.05 × regime_alignment

Modifiers:
  ML Hold penalty:  direction == 0 → composite × 0.30
  Symbol fitness:   composite × (0.5 + fitness) → [0.6×, 1.45×]
  Min composite:    0.15 | Top-N: 5 candidates`}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Breakout Scanner" subtitle="6-detector weighted composite">
      <MermaidDiagram definition={breakoutScanner} />
      <FormulaBlock
        label="6-Detector Composite Formula"
        formula={`COMPOSITE = 0.25 × squeeze
          + 0.25 × volume_surge
          + 0.15 × range_contraction
          + 0.15 × relative_strength
          + 0.15 × pivot_breakout
          + 0.05 × institutional_flow

Bonuses: Squeeze + Volume fired → ×1.30
Post-filter: composite < 0.20 → filtered out
Top-N: 8 breakout signals`}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Kelly Position Sizer" subtitle="7-step multiplication chain">
      <MermaidDiagram definition={kellySizer} />
      <FormulaBlock
        label="Kelly Sizing Formula"
        formula={`target_weight = (kelly_raw × 0.5)                    # Half-Kelly
              × drawdown_scale(dd)                     # [0.1, 1.0]
              × vol_scale(stock_vol)                   # [0, 2.0]
              × regime_scale(regime)                   # [0.1, 1.2]
              × confidence_scale(conf, ml_trained)     # [0.3, 1.5]
              × breakout_bonus(brk_score, ml_trained)  # [1.0, 2.0]

Caps: 10% per position | 95% portfolio | Min $2,000`}
      />
      <ThresholdTable
        data={regimeScales}
        columns={[
          { title: 'Regime', dataIndex: 'regime', key: 'regime' },
          { title: 'Kelly Scale', dataIndex: 'scale', key: 'scale' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Adaptive Exit Engine" subtitle="8-priority cascade with regime thresholds">
      <MermaidDiagram definition={adaptiveExitCascade} />
      <ThresholdTable
        data={exitRegimeParams}
        columns={[
          { title: 'Regime', dataIndex: 'regime', key: 'regime' },
          { title: 'Stop ATR', dataIndex: 'stopATR', key: 'stopATR' },
          { title: 'TP R-Multiple', dataIndex: 'tpRMultiple', key: 'tpRMultiple' },
          { title: 'Trail ATR', dataIndex: 'trailATR', key: 'trailATR' },
          { title: 'Max Bars', dataIndex: 'maxBars', key: 'maxBars' },
          { title: 'Decay Start', dataIndex: 'decayStart', key: 'decayStart' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Regime Detection" subtitle="signals → softmax → EMA → label">
      <MermaidDiagram definition={regimeDetection} />
      <FormulaBlock
        label="Regime Detection Pipeline"
        formula={`4 Signals → Raw Scores (additive):
  trending_up:   +2 (strong trend) or +1 (above SMA)
  trending_down: +2 or +1
  chop:          +1.5 (no trend) or +0.5 (near SMA)
  high_vol:      +2 (high ATR) or +1 (high returns vol)
  low_vol:       +1.5 (low ATR)
  stress:        +2 (vol anomaly + high ATR) or +1

Scores → Softmax → EMA Smoothing (α=0.3) → argmax → Label`}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Self-Evolution Engine" subtitle="10-step parameter evolution loop">
      <MermaidDiagram definition={selfEvolution} />
      <FormulaBlock
        label="EMA Update (Safety-Bounded)"
        formula={`delta = α × new + (1-α) × old - old
max_delta = |old| × 0.20 + 0.005     # max 20% shift per step
clamped_delta = clamp(delta, -max_delta, max_delta)
result = old + clamped_delta`}
      />
    </CollapsibleSection>
  </div>
);

export default AlgorithmEngineTab;
