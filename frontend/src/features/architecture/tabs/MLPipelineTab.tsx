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
    </CollapsibleSection>
  </div>
);

export default MLPipelineTab;
