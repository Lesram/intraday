import { Typography } from 'antd';
import MermaidDiagram from '../components/MermaidDiagram';
import CollapsibleSection from '../components/CollapsibleSection';
import ThresholdTable from '../components/ThresholdTable';
import {
  orderExecutionSequence, outboxDLQ, orderGuardrails, circuitBreaker,
} from '../data/mermaidDefinitions';
import { colors } from '@styles/theme';

const { Title, Text } = Typography;

const outboxConfig = [
  { param: 'poll_interval', value: '0.1s (100ms)', purpose: 'HFT-optimized polling' },
  { param: 'max_retries', value: '5', purpose: 'Before DLQ' },
  { param: 'initial_backoff', value: '1.0s', purpose: 'First retry delay' },
  { param: 'max_backoff', value: '300s', purpose: 'Cap on retry delay' },
  { param: 'jitter_factor', value: '0.1', purpose: 'Prevents thundering herd' },
];

const cbConfig = [
  { param: 'failure_threshold', value: '5', purpose: 'Failures to trip' },
  { param: 'success_threshold', value: '3', purpose: 'Successes to recover' },
  { param: 'timeout_seconds', value: '60', purpose: 'Time before half-open attempt' },
  { param: 'window_seconds', value: '300', purpose: 'Failure counting window' },
  { param: 'loss_threshold_pct', value: '5%', purpose: 'Daily PnL loss kill switch' },
];

const guardrailLayers = [
  { layer: '1', check: 'Trading paused?', rejection: 'REJECT' },
  { layer: '2', check: 'Within trading window? (9:30-16:00 ET)', rejection: 'REJECT' },
  { layer: '3', check: 'Symbol in whitelist?', rejection: 'REJECT' },
  { layer: '4', check: 'Order size <= max? (100 shares)', rejection: 'REJECT' },
  { layer: '5', check: 'Daily order count <= max? (100/day)', rejection: 'REJECT' },
  { layer: '6', check: 'Daily notional <= cap? ($10K)', rejection: 'REJECT' },
  { layer: '7', check: 'Rate limit? (10/min)', rejection: 'REJECT' },
  { layer: '8', check: 'Circuit breaker open?', rejection: 'REJECT' },
];

const InfrastructureTab = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <Title level={4} style={{ margin: 0 }}>Infrastructure & Order Execution</Title>

    <CollapsibleSection title="Order Execution Sequence" subtitle="LiveEngine → OrderService → Outbox → Alpaca → Stream" defaultOpen>
      <MermaidDiagram definition={orderExecutionSequence} />
      <Text style={{ color: colors.text.tertiary, fontSize: 12, display: 'block', marginTop: 8 }}>
        Atomicity: Order record + Outbox event created in the same DB transaction. Both persist or neither.
      </Text>
    </CollapsibleSection>

    <CollapsibleSection title="Transactional Outbox + DLQ" subtitle="At-least-once delivery with retry cascade">
      <MermaidDiagram definition={outboxDLQ} />
      <ThresholdTable
        data={outboxConfig}
        columns={[
          { title: 'Parameter', dataIndex: 'param', key: 'param', render: (v: string) => <code>{v}</code> },
          { title: 'Value', dataIndex: 'value', key: 'value' },
          { title: 'Purpose', dataIndex: 'purpose', key: 'purpose' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="8-Layer Order Guardrails" subtitle="Pre-submission validation gate cascade">
      <MermaidDiagram definition={orderGuardrails} />
      <ThresholdTable
        data={guardrailLayers}
        columns={[
          { title: 'Layer', dataIndex: 'layer', key: 'layer', width: 60 },
          { title: 'Check', dataIndex: 'check', key: 'check' },
          { title: 'On Fail', dataIndex: 'rejection', key: 'rejection',
            render: (v: string) => <Text style={{ color: colors.semantic.loss }}>{v}</Text> },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Circuit Breaker State Machine" subtitle="CLOSED ↔ OPEN ↔ HALF_OPEN">
      <MermaidDiagram definition={circuitBreaker} />
      <ThresholdTable
        data={cbConfig}
        columns={[
          { title: 'Parameter', dataIndex: 'param', key: 'param', render: (v: string) => <code>{v}</code> },
          { title: 'Value', dataIndex: 'value', key: 'value' },
          { title: 'Purpose', dataIndex: 'purpose', key: 'purpose' },
        ]}
      />
    </CollapsibleSection>
  </div>
);

export default InfrastructureTab;
