import { Typography, Tag, Card, Steps } from 'antd';
import MermaidDiagram from '../components/MermaidDiagram';
import CollapsibleSection from '../components/CollapsibleSection';
import ThresholdTable from '../components/ThresholdTable';
import { mlPipeline, trainingOrchestrator, driftDetection } from '../data/mermaidDefinitions';
import { colors } from '@styles/theme';

const { Title, Text } = Typography;

const promotionStages = [
  { stage: 'SHADOW', riskCap: '0%', minDuration: '1 hour', desc: 'Model runs but no orders placed', color: colors.text.tertiary },
  { stage: 'PAPER_EXECUTE', riskCap: '20%', minDuration: '24 hours', desc: 'Paper trades only', color: colors.brand.primary },
  { stage: 'CANARY', riskCap: '5%', minDuration: '24 hours', desc: 'Small real allocation', color: colors.semantic.warning },
  { stage: 'RAMP', riskCap: '15%', minDuration: '48 hours', desc: 'Gradual ramp-up', color: colors.semantic.warning },
  { stage: 'ACTIVE', riskCap: '25%', minDuration: '-', desc: 'Full production', color: colors.semantic.profit },
  { stage: 'ROLLED_BACK', riskCap: '0%', minDuration: '-', desc: 'Emergency stop', color: colors.semantic.loss },
];

const rollbackTriggers = [
  { trigger: 'Max drawdown', threshold: '8%', action: 'Immediate rollback' },
  { trigger: 'Max slippage', threshold: '50 bps', action: 'Immediate rollback' },
  { trigger: 'Max turnover ratio', threshold: '10.0x', action: 'Immediate rollback' },
  { trigger: 'Max regime churn rate', threshold: '0.50', action: 'Immediate rollback' },
];

const brainContents = [
  { item: 'ML models', detail: 'Classifier + regressor, HMAC-signed via secure_pickle' },
  { item: 'Learning state', detail: 'learning_state.json + trade history (CSV) + equity curve (CSV)' },
  { item: 'Evolved params', detail: 'evolved_params.json + governance_state.json' },
  { item: 'Regime state', detail: 'regime_state.json' },
  { item: 'Extra counters', detail: 'Exit levels, entry metadata, Kelly stats, universe, ML calibration, tick_count' },
  { item: 'Manifest', detail: 'Format version, generation, trade count, best Sharpe' },
];

const validationGates = [
  { gate: '1', check: 'NaN/Inf in evolved_params' },
  { gate: '2', check: 'Alpha weight normalization (sum ≈ 1.0, tolerance 0.05)' },
  { gate: '3', check: 'Breakout weight normalization check' },
  { gate: '4', check: 'ML model sanity (predict_proba test on zeros)' },
  { gate: '5', check: 'Feature schema drift detection (added/removed features)' },
];

const stalenessDimensions = [
  { dimension: '1. Age', detail: 'Days since training' },
  { dimension: '2. Performance decay', detail: 'Accuracy drop %' },
  { dimension: '3. Feature drift', detail: 'PSI score' },
  { dimension: '4. Prediction drift', detail: 'Distribution shift' },
  { dimension: '5. Regime change', detail: 'New regime since training' },
];

const driftThresholds = [
  { trigger: 'PSI >= 0.15', action: 'Feature drift detected → early retrain' },
  { trigger: 'Performance drop >= 2%', action: 'min_return_drop trigger → retrain' },
  { trigger: 'Negative recent returns', action: 'Fallback retrain' },
];

const MLPipelineTab = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <Title level={4} style={{ margin: 0 }}>ML Deployment Pipeline</Title>

    <CollapsibleSection title="6-Stage Promotion Ladder" subtitle="SHADOW → PAPER → CANARY → RAMP → ACTIVE" defaultOpen>
      <Steps
        direction="vertical"
        size="small"
        current={-1}
        items={promotionStages.map((s) => ({
          title: (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Text strong style={{ color: s.color }}>{s.stage}</Text>
              <Tag>{s.riskCap} exposure</Tag>
              {s.minDuration !== '-' && <Tag color="default">{s.minDuration} min</Tag>}
            </div>
          ),
          description: <Text style={{ color: colors.text.tertiary, fontSize: 12 }}>{s.desc}</Text>,
          status: 'wait' as const,
        }))}
      />
      <Card size="small" style={{ background: colors.backgrounds.tertiary, marginTop: 16 }}>
        <Text strong style={{ color: colors.semantic.loss }}>Rollback Triggers</Text>
        <ThresholdTable
          data={rollbackTriggers}
          columns={[
            { title: 'Trigger', dataIndex: 'trigger', key: 'trigger' },
            { title: 'Threshold', dataIndex: 'threshold', key: 'threshold' },
            { title: 'Action', dataIndex: 'action', key: 'action',
              render: (v: string) => <Text style={{ color: colors.semantic.loss }}>{v}</Text> },
          ]}
        />
      </Card>
    </CollapsibleSection>

    <CollapsibleSection title="8-Stage ML Pipeline" subtitle="Ingestion → Features → Selection → Split → Train → Validate → Gate → Promote">
      <MermaidDiagram definition={mlPipeline} />
    </CollapsibleSection>

    <CollapsibleSection title="Training Orchestrator" subtitle="Background + sync fallback with stuck detection">
      <MermaidDiagram definition={trainingOrchestrator} />
      <Card size="small" style={{ background: colors.backgrounds.tertiary, marginTop: 12 }}>
        <Text strong style={{ color: colors.text.primary }}>Validation Gate</Text>
        <div style={{ marginTop: 8, fontSize: 13, color: colors.text.secondary }}>
          <div>Composite score = hit_rate x 0.4 + accuracy x 0.3 + (dir_acc - 0.5) x 0.6</div>
          <div style={{ marginTop: 4 }}>No old model: accept if score {'>'} 0.25</div>
          <div>Old model exists: accept if improvement {'>='} 5% OR (score {'>='} 0.40 AND hit_rate {'>='} 0.48)</div>
        </div>
      </Card>
    </CollapsibleSection>

    <CollapsibleSection title="Drift Detection & Retrain Trigger" subtitle="PSI-based feature drift + regime churn monitoring">
      <MermaidDiagram definition={driftDetection} />
      <ThresholdTable
        data={driftThresholds}
        columns={[
          { title: 'Trigger', dataIndex: 'trigger', key: 'trigger', render: (v: string) => <code>{v}</code> },
          { title: 'Action', dataIndex: 'action', key: 'action' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Brain Persistence" subtitle="Format v2, HMAC-signed, 5 validation gates, walk-forward 0.95">
      <Card size="small" style={{ background: colors.backgrounds.tertiary, marginBottom: 12 }}>
        <Text strong style={{ color: colors.text.primary }}>Storage</Text>
        <div style={{ marginTop: 8, fontSize: 13, color: colors.text.secondary }}>
          <div>Directory: organism_brain/ (gitignored)</div>
          <div>Format: JSON + CSV files (v2, auto-migrates v1 → v2)</div>
          <div>Save frequency: every 20 ticks (~3.3 min) + event-driven (after fill reconciliation)</div>
          <div>Gate: walk-forward check must pass (regression threshold 0.95)</div>
          <div>If gate rejects: best_sharpe decayed by 5% to prevent permanent blocking</div>
          <div>Trade history: archived to gzipped CSV when {'>'} 10,000 rows, max 10 archives</div>
        </div>
      </Card>
      <ThresholdTable
        data={brainContents}
        columns={[
          { title: 'Item', dataIndex: 'item', key: 'item', render: (v: string) => <Text strong>{v}</Text> },
          { title: 'Detail', dataIndex: 'detail', key: 'detail' },
        ]}
      />
      <Text strong style={{ color: colors.text.primary, display: 'block', marginTop: 16, marginBottom: 8 }}>
        5 Validation Gates (on load)
      </Text>
      <ThresholdTable
        data={validationGates}
        columns={[
          { title: '#', dataIndex: 'gate', key: 'gate', width: 40 },
          { title: 'Integrity Check', dataIndex: 'check', key: 'check' },
        ]}
      />
    </CollapsibleSection>

    <CollapsibleSection title="Staleness Detector" subtitle="5 dimensions: age → perf → drift → prediction → regime">
      <Card size="small" style={{ background: colors.backgrounds.tertiary, marginBottom: 12 }}>
        <Text strong style={{ color: colors.text.primary }}>Staleness Levels</Text>
        <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
          <Tag color="green">fresh</Tag>
          <Text style={{ color: colors.text.tertiary }}>→</Text>
          <Tag color="gold">aging</Tag>
          <Text style={{ color: colors.text.tertiary }}>→</Text>
          <Tag color="orange">stale</Tag>
          <Text style={{ color: colors.text.tertiary }}>→</Text>
          <Tag color="red">critical</Tag>
        </div>
      </Card>
      <ThresholdTable
        data={stalenessDimensions}
        columns={[
          { title: 'Dimension', dataIndex: 'dimension', key: 'dimension', render: (v: string) => <Text strong>{v}</Text> },
          { title: 'Detail', dataIndex: 'detail', key: 'detail' },
        ]}
      />
    </CollapsibleSection>
  </div>
);

export default MLPipelineTab;
