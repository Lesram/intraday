import { Card, Typography, Tag, Row, Col, Descriptions } from 'antd';
import { colors } from '@styles/theme';

const { Title, Text } = Typography;

const tiers = [
  {
    name: 'Frontend',
    color: colors.brand.primary,
    items: ['React + Vite + Ant Design', 'TypeScript', 'Port 5173 (dev)'],
    desc: 'Decision Dashboard, Diagnostics Panel, Organism Dashboard',
  },
  {
    name: 'Backend',
    color: colors.semantic.profit,
    items: ['FastAPI + async SQLAlchemy', 'Python 3.12', 'Port 8000'],
    desc: '152+ REST endpoints, Socket.IO, WebSocket Manager',
  },
  {
    name: 'Data Layer',
    color: colors.semantic.warning,
    items: ['PostgreSQL 16 (24 tables)', 'Redis 7 (cache/queue)'],
    desc: 'Docker containers, AOF persistence, allkeys-lru',
  },
  {
    name: 'External',
    color: colors.brand.secondary,
    items: ['Alpaca Markets API v2', 'Paper trading mode'],
    desc: 'REST: orders/positions/account, WS: trade updates + market data',
  },
];

const dataFlows = [
  { path: 'Order Execution', direction: 'OUT → IN', desc: 'Engine → DB Order → Outbox → Alpaca REST → WS Fill → DB → Socket.IO → Frontend' },
  { path: 'Market Data', direction: 'IN', desc: 'Alpaca WS (bars) → StreamingProvider → Ring Buffer → Engine' },
  { path: 'Historical Data', direction: 'IN', desc: 'Alpaca REST → DataClient → Feature Engineering → ML/Alpha' },
  { path: 'Brain State', direction: 'LOCAL', desc: 'Engine State → JSON files (organism_brain/) → Load on restart' },
];

const techStack = [
  { layer: 'Frontend', tech: 'React + Vite + Ant Design', version: 'TypeScript' },
  { layer: 'Backend', tech: 'FastAPI + async SQLAlchemy', version: 'Python 3.12' },
  { layer: 'Database', tech: 'PostgreSQL', version: '16-alpine' },
  { layer: 'Cache/Queue', tech: 'Redis', version: '7-alpine' },
  { layer: 'ML', tech: 'XGBoost + LightGBM + scikit-learn', version: '-' },
  { layer: 'Broker', tech: 'Alpaca Markets API v2', version: 'Paper trading' },
  { layer: 'Observability', tech: 'Prometheus + Grafana + OpenTelemetry', version: 'Optional' },
  { layer: 'Container', tech: 'Docker Compose', version: '3 core + 3 observability' },
];

interface SystemOverviewTabProps {
  onNavigateTab?: (tab: string) => void;
}

const SystemOverviewTab = ({ onNavigateTab }: SystemOverviewTabProps) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
    <Title level={4} style={{ margin: 0 }}>4-Tier System Architecture</Title>

    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {tiers.map((tier) => (
        <Card
          key={tier.name}
          size="small"
          style={{
            background: colors.backgrounds.tertiary,
            borderLeft: `4px solid ${tier.color}`,
            cursor: onNavigateTab ? 'pointer' : 'default',
          }}
          onClick={() => {
            if (!onNavigateTab) return;
            if (tier.name === 'Backend') onNavigateTab('tick');
            else if (tier.name === 'External') onNavigateTab('infra');
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <Text strong style={{ color: tier.color, fontSize: 16 }}>{tier.name}</Text>
            {tier.items.map((item) => (
              <Tag key={item} color="default" style={{ fontSize: 11 }}>{item}</Tag>
            ))}
          </div>
          <Text style={{ color: colors.text.tertiary, fontSize: 13 }}>{tier.desc}</Text>
        </Card>
      ))}
    </div>

    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center' }}>
      {['Engine Decision', '→', 'DB Order', '→', 'Outbox', '→', 'Alpaca REST'].map((label, i) => (
        label === '→' ? (
          <Text key={i} style={{ color: colors.text.tertiary, fontSize: 20 }}>→</Text>
        ) : (
          <Tag key={i} color="blue" style={{ fontSize: 13, padding: '4px 12px' }}>{label}</Tag>
        )
      ))}
    </div>
    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'center' }}>
      {['Alpaca Fill', '→', 'WebSocket', '→', 'DB Update', '→', 'Socket.IO', '→', 'Frontend'].map((label, i) => (
        label === '→' ? (
          <Text key={i} style={{ color: colors.text.tertiary, fontSize: 20 }}>→</Text>
        ) : (
          <Tag key={i} color="green" style={{ fontSize: 13, padding: '4px 12px' }}>{label}</Tag>
        )
      ))}
    </div>

    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}>
        <Card title="Technology Stack" size="small" style={{ background: colors.backgrounds.secondary }}>
          <Descriptions column={1} size="small" bordered>
            {techStack.map((row) => (
              <Descriptions.Item key={row.layer} label={row.layer}>
                <Text>{row.tech}</Text>
                <Text style={{ color: colors.text.tertiary, marginLeft: 8 }}>{row.version}</Text>
              </Descriptions.Item>
            ))}
          </Descriptions>
        </Card>
      </Col>
      <Col xs={24} lg={12}>
        <Card title="Data Flow Paths" size="small" style={{ background: colors.backgrounds.secondary }}>
          {dataFlows.map((flow) => (
            <div key={flow.path} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                <Text strong style={{ color: colors.text.primary }}>{flow.path}</Text>
                <Tag color={flow.direction === 'IN' ? 'green' : flow.direction === 'LOCAL' ? 'default' : 'blue'}>
                  {flow.direction}
                </Tag>
              </div>
              <Text style={{ color: colors.text.tertiary, fontSize: 12 }}>{flow.desc}</Text>
            </div>
          ))}
        </Card>
      </Col>
    </Row>

    <Card title="Dual Engine Paths (Mutually Exclusive)" size="small" style={{ background: colors.backgrounds.secondary }}>
      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Card size="small" style={{ background: colors.backgrounds.tertiary, borderColor: colors.semantic.profit }}>
            <Text strong style={{ color: colors.semantic.profit }}>Path A: OrganismScheduler</Text>
            <div style={{ marginTop: 8, color: colors.text.secondary, fontSize: 13 }}>
              <div>ENABLE_ORGANISM_SCHEDULER=1</div>
              <div>OrganismLiveEngine tick loop (10s)</div>
              <div>ML → Alpha → Kelly → Exits</div>
            </div>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card size="small" style={{ background: colors.backgrounds.tertiary, borderColor: colors.text.tertiary }}>
            <Text strong style={{ color: colors.text.secondary }}>Path B: MultiStrategyLiveScheduler</Text>
            <div style={{ marginTop: 8, color: colors.text.tertiary, fontSize: 13 }}>
              <div>MULTI_STRATEGY_LIVE_ENABLED=1</div>
              <div>10 independent strategies (300s)</div>
              <div>OrganismRunner governance hooks</div>
            </div>
          </Card>
        </Col>
      </Row>
    </Card>
  </div>
);

export default SystemOverviewTab;
