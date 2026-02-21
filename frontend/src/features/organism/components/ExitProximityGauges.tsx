import { Card, Col, Progress, Row, Tag, Typography } from 'antd';
import type { ExitProximity } from '../organismApi';

const { Text } = Typography;

const gaugeColor = (dist: number): string => {
  if (dist < 15) return '#ff4d4f';
  if (dist < 30) return '#faad14';
  return '#52c41a';
};

const ExitProximityGauges = ({ data }: { data: ExitProximity | null }) => {
  if (!data) {
    return (
      <Card title="Exit Proximity" size="small">
        <Text type="secondary">Select a position to see exit proximity</Text>
      </Card>
    );
  }

  const exits = [
    { label: 'Stop Loss', dist: data.exits.stop_loss.distance_pct, level: data.exits.stop_loss.level, active: true },
    { label: 'Take Profit', dist: data.exits.take_profit.distance_pct, level: data.exits.take_profit.level, active: true },
    { label: 'Trailing Stop', dist: data.exits.trailing_stop.distance_pct, level: data.exits.trailing_stop.level, active: data.exits.trailing_stop.active },
    { label: 'Partial TP', dist: data.exits.partial_tp.distance_pct, level: data.exits.partial_tp.level, active: !data.exits.partial_tp.taken },
  ];

  return (
    <Card title={`Exit Proximity: ${data.symbol}`} size="small">
      <Row gutter={[8, 8]}>
        {exits.map((exit) => (
          <Col span={12} key={exit.label}>
            <div style={{ marginBottom: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text style={{ fontSize: 11, fontWeight: 500 }}>{exit.label}</Text>
                {!exit.active && <Tag style={{ fontSize: 10 }}>Inactive</Tag>}
              </div>
              <Progress
                percent={Math.min(100 - Math.min(exit.dist, 100), 100)}
                size="small"
                strokeColor={exit.active ? gaugeColor(exit.dist) : '#d9d9d9'}
                format={() => `${exit.dist.toFixed(1)}%`}
              />
              <Text type="secondary" style={{ fontSize: 10 }}>Level: ${exit.level.toFixed(2)}</Text>
            </div>
          </Col>
        ))}
        <Col span={12}>
          <div>
            <Text style={{ fontSize: 11, fontWeight: 500 }}>Time Exit</Text>
            <Progress
              percent={data.exits.time.max_bars > 0 ? (data.exits.time.bars_held / data.exits.time.max_bars) * 100 : 0}
              size="small"
              strokeColor={data.exits.time.bars_held / Math.max(data.exits.time.max_bars, 1) > 0.8 ? '#ff4d4f' : '#1890ff'}
              format={() => data.exits.time.max_bars > 0 ? `${data.exits.time.bars_held}/${data.exits.time.max_bars}` : 'No limit'}
            />
          </div>
        </Col>
        <Col span={12}>
          <div>
            <Text style={{ fontSize: 11, fontWeight: 500 }}>Nearest Exit</Text>
            <div style={{ marginTop: 4 }}>
              <Tag color={data.nearest_exit_distance_pct < 15 ? 'error' : 'processing'}>
                {data.nearest_exit.replace('_', ' ')} ({data.nearest_exit_distance_pct.toFixed(1)}%)
              </Tag>
            </div>
          </div>
        </Col>
      </Row>
    </Card>
  );
};

export default ExitProximityGauges;
