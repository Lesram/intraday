import { Card, Progress, Typography } from 'antd';
import type { RegimeProbabilities } from '../organismApi';

const { Text } = Typography;

const REGIME_COLORS: Record<string, string> = {
  trending_up: '#52c41a', trending: '#73d13d', normal: '#1890ff',
  trending_down: '#faad14', chop: '#fa8c16', high_vol: '#ff7a45',
  stress: '#ff4d4f', crisis: '#cf1322', low_vol: '#722ed1',
};

const RegimeProbabilityPanel = ({ regime }: { regime: RegimeProbabilities | null }) => {
  if (!regime || Object.keys(regime.probabilities).length === 0) {
    return (
      <Card title="Regime Probabilities" size="small">
        <Text type="secondary">No regime probability data</Text>
      </Card>
    );
  }

  const sorted = Object.entries(regime.probabilities).sort((a, b) => b[1] - a[1]);

  return (
    <Card title="Regime Probabilities" size="small">
      {sorted.map(([label, prob]) => (
        <div key={label} style={{ marginBottom: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
            <Text style={{ fontSize: 12, fontWeight: label === regime.primary ? 600 : 400 }}>
              {label.replace('_', ' ')}
              {label === regime.primary && ' (active)'}
            </Text>
            <Text type="secondary" style={{ fontSize: 11 }}>{(prob * 100).toFixed(1)}%</Text>
          </div>
          <Progress
            percent={prob * 100}
            size="small"
            showInfo={false}
            strokeColor={REGIME_COLORS[label] ?? '#999'}
          />
        </div>
      ))}
      <div style={{ marginTop: 8 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          Confidence: {(regime.confidence * 100).toFixed(1)}%
        </Text>
      </div>
    </Card>
  );
};

export default RegimeProbabilityPanel;
