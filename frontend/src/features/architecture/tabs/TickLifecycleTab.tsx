import { Typography, Tag, Card, Row, Col } from 'antd';
import MermaidDiagram from '../components/MermaidDiagram';
import CollapsibleSection from '../components/CollapsibleSection';
import FormulaBlock from '../components/FormulaBlock';
import ThresholdTable from '../components/ThresholdTable';
import { governanceDecisionTree, exitDecisionTree, fillReconciliation, entryScanningPipeline } from '../data/mermaidDefinitions';
import { cooldowns } from '../data/thresholds';
import { colors } from '@styles/theme';

const { Title, Text } = Typography;

const phases = [
  { id: 0, name: 'Housekeeping', desc: 'Expire cooldowns, stream health check', always: true },
  { id: 1, name: 'Governance Gate', desc: 'Halt check, drawdown kill, freeze adaptation', always: true },
  { id: 2, name: 'Data Acquisition', desc: 'Fetch bars + compute 79 features per symbol', always: true },
  { id: 3, name: 'Regime Detection', desc: '3-tier priority: cross-asset → SPY → aggregate', always: true },
  { id: 4, name: 'Portfolio State', desc: 'Get positions + equity, drawdown kill check', always: true },
  { id: 5, name: 'Exit Decisions', desc: '8-priority cascade for every open position', always: true },
  { id: 6, name: 'Pyramid Checks', desc: 'Layer adds, anti-pyramid loss cutting', always: false },
  { id: 7, name: 'Entry Scanning', desc: 'Alpha + Breakout + ML → 8 filter gates', always: false },
  { id: 8, name: 'Kelly Sizing', desc: '7-step multiplication chain → shares', always: false },
  { id: 9, name: 'Order Submission', desc: 'Market DAY with idempotency keys', always: false },
  { id: 10, name: 'Fill Reconciliation', desc: 'Detect closed + orphaned positions', always: true },
  { id: 11, name: 'Retrain & Evolve', desc: 'ML fit + 10 evolution sub-steps', always: false },
  { id: 12, name: 'Brain Persistence', desc: 'Save every 20 ticks with walk-forward gate', always: true },
];

const preScanGates = [
  { gate: 'Warmup gate', timing: 'Step 1.1, before data fetch', condition: 'First 5 ticks after engine start', variable: 'entries_blocked' },
  { gate: 'Equity-zero gate', timing: 'Step 4, after data + regime', condition: '3+ consecutive zero-equity readings', variable: 'entries_blocked' },
  { gate: 'Opening 30-min block', timing: 'After exit checks', condition: '9:30-10:00 AM ET (intraday only)', variable: 'entries_blocked' },
  { gate: 'Regime sit-out', timing: 'After exit checks', condition: 'high_vol/stress + all ML bearish', variable: '_regime_sit_out' },
  { gate: 'Entry throttle', timing: 'After exit checks', condition: '3 entries in last hour (rolling 3600s)', variable: '_throttled' },
];

const TickLifecycleTab = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
    <Title level={4} style={{ margin: 0 }}>13-Phase Tick Pipeline (~10s)</Title>
    <Text style={{ color: colors.text.tertiary }}>
      Exits ALWAYS run, even when governance has halted trading. Only new entries are blocked.
    </Text>

    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {phases.map((phase) => (
        <Card
          key={phase.id}
          size="small"
          style={{
            background: colors.backgrounds.tertiary,
            borderLeft: `4px solid ${phase.always ? colors.semantic.profit : colors.brand.primary}`,
          }}
        >
          <Row align="middle" gutter={12}>
            <Col flex="60px">
              <Tag color={phase.always ? 'green' : 'blue'} style={{ margin: 0, fontWeight: 600 }}>
                [{phase.id}]
              </Tag>
            </Col>
            <Col flex="180px">
              <Text strong style={{ color: colors.text.primary }}>{phase.name}</Text>
            </Col>
            <Col flex="auto">
              <Text style={{ color: colors.text.secondary, fontSize: 13 }}>{phase.desc}</Text>
            </Col>
            <Col>
              <Tag color={phase.always ? 'green' : 'blue'} style={{ fontSize: 11 }}>
                {phase.always ? 'ALWAYS' : 'IF entries OK'}
              </Tag>
            </Col>
          </Row>
        </Card>
      ))}
    </div>

    <CollapsibleSection title="Cooldown Constants" subtitle="Timer values for anti-duplicate protection">
      <ThresholdTable
        data={cooldowns}
        columns={[
          { title: 'Cooldown', dataIndex: 'cooldown', key: 'cooldown', render: (v: string) => <code>{v}</code> },
          { title: 'Ticks', dataIndex: 'ticks', key: 'ticks' },
          { title: 'Real Time', dataIndex: 'realTime', key: 'realTime' },
          { title: 'Purpose', dataIndex: 'purpose', key: 'purpose' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Phase 1: Governance Decision Tree" subtitle="Halt/drawdown/freeze checks" defaultOpen>
      <MermaidDiagram definition={governanceDecisionTree} />
    </CollapsibleSection>

    <CollapsibleSection title="Phase 5: Exit Decision Tree" subtitle="8-priority cascade" defaultOpen>
      <MermaidDiagram definition={exitDecisionTree} />
    </CollapsibleSection>

    <CollapsibleSection title="Pre-Scan Entry Gates" subtitle="5 independent gates scattered across the tick">
      <ThresholdTable
        data={preScanGates}
        columns={[
          { title: 'Gate', dataIndex: 'gate', key: 'gate', render: (v: string) => <Text strong>{v}</Text> },
          { title: 'Timing', dataIndex: 'timing', key: 'timing' },
          { title: 'Condition', dataIndex: 'condition', key: 'condition' },
          { title: 'Variable', dataIndex: 'variable', key: 'variable', render: (v: string) => <code>{v}</code> },
        ]}
      />
      <Card size="small" style={{ background: colors.backgrounds.tertiary, marginTop: 12 }}>
        <Text style={{ color: colors.text.secondary, fontSize: 13 }}>
          Final gating: <code>if not entries_blocked and not _regime_sit_out and not _throttled</code>
          <br />These are 3 independent gating variables, not a single entries_blocked flag.
        </Text>
      </Card>
    </CollapsibleSection>

    <CollapsibleSection title="Phase 7: Entry Scanning Pipeline" subtitle="7-step scan with 8 filter gates">
      <MermaidDiagram definition={entryScanningPipeline} />
      <FormulaBlock
        label="Blended Confidence (Additive)"
        formula={`confidence = 0.50 × ML_confidence
           + 0.30 × breakout_score
           + 0.20 × min(tension, 1.0)

NOTE: ML = 0.0 when no signal (not 0.5 like old multiplicative formula)
Weighted sum of [0,1] inputs stays in [0,1] — no cap needed`}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Phase 10: Fill Reconciliation" subtitle="Detect closed + orphaned positions">
      <MermaidDiagram definition={fillReconciliation} />
    </CollapsibleSection>
  </div>
);

export default TickLifecycleTab;
