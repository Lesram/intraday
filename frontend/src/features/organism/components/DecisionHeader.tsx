import { Card, Col, Row, Statistic, Tag, Tooltip } from 'antd';
import { ClockCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import type { DecisionSnapshot } from '../organismApi';

const REGIME_COLORS: Record<string, string> = {
  trending_up: '#52c41a', trending: '#73d13d', normal: '#1890ff',
  trending_down: '#faad14', chop: '#fa8c16', high_vol: '#ff7a45',
  stress: '#ff4d4f', crisis: '#cf1322',
};

const DecisionHeader = ({ snapshot }: { snapshot: DecisionSnapshot | null }) => {
  if (!snapshot) {
    return <Card title="Decision Header" size="small"><span>No decision data yet</span></Card>;
  }

  const regime = snapshot.regime.primary;
  const regimeColor = REGIME_COLORS[regime] ?? '#999';

  return (
    <Card title="Decision Header" size="small">
      <Row gutter={[12, 12]}>
        <Col span={4}>
          <Statistic title="Tick" value={snapshot.tick_number} prefix={<ThunderboltOutlined />} valueStyle={{ fontSize: 18 }} />
        </Col>
        <Col span={5}>
          <Tooltip title={`Confidence: ${(snapshot.regime.confidence * 100).toFixed(1)}%`}>
            <Statistic
              title="Regime"
              valueRender={() => <Tag color={regimeColor}>{regime.replace('_', ' ')}</Tag>}
            />
          </Tooltip>
        </Col>
        <Col span={4}>
          <Statistic title="Positions" value={`${snapshot.open_positions}/${snapshot.max_positions}`} valueStyle={{ fontSize: 18 }} />
        </Col>
        <Col span={4}>
          <Statistic title="Alpha Scored" value={snapshot.alpha_scores.length} valueStyle={{ fontSize: 18 }} />
        </Col>
        <Col span={4}>
          <Statistic title="Orders" value={snapshot.filtering.orders_submitted} valueStyle={{ fontSize: 18 }} />
        </Col>
        <Col span={3}>
          <Statistic title="Duration" value={`${snapshot.duration_s.toFixed(2)}s`} prefix={<ClockCircleOutlined />} valueStyle={{ fontSize: 14 }} />
        </Col>
      </Row>
    </Card>
  );
};

export default DecisionHeader;
