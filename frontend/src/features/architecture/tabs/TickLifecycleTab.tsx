import { Typography, Tag, Card, Row, Col } from 'antd';
import MermaidDiagram from '../components/MermaidDiagram';
import CollapsibleSection from '../components/CollapsibleSection';
import ThresholdTable from '../components/ThresholdTable';
import { governanceDecisionTree, exitDecisionTree, fillReconciliation } from '../data/mermaidDefinitions';
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
  { id: 7, name: 'Entry Scanning', desc: 'Alpha + Breakout + ML → 7 filter gates', always: false },
  { id: 8, name: 'Kelly Sizing', desc: '7-step multiplication chain → shares', always: false },
  { id: 9, name: 'Order Submission', desc: 'Market IOC with idempotency keys', always: false },
  { id: 10, name: 'Fill Reconciliation', desc: 'Detect closed + orphaned positions', always: true },
  { id: 11, name: 'Retrain & Evolve', desc: 'ML fit + 10 evolution sub-steps', always: false },
  { id: 12, name: 'Brain Persistence', desc: 'Save every 50 ticks with walk-forward gate', always: true },
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

    <CollapsibleSection title="Phase 10: Fill Reconciliation" subtitle="Detect closed + orphaned positions">
      <MermaidDiagram definition={fillReconciliation} />
    </CollapsibleSection>
  </div>
);

export default TickLifecycleTab;
