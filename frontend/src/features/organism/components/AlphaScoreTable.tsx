import { Table, Tag, Tooltip, Typography } from 'antd';
import type { AlphaFactorScore } from '../organismApi';

const { Text } = Typography;

const nearThresholdStyle = (value: number, threshold: number): React.CSSProperties => {
  const dist = Math.abs(value - threshold);
  if (dist < threshold * 0.1) return { border: '1px solid #faad14', borderRadius: 2, padding: '0 4px' };
  return {};
};

const AlphaScoreTable = ({
  data,
  onRowClick,
}: {
  data: AlphaFactorScore[];
  onRowClick?: (symbol: string) => void;
}) => {
  if (data.length === 0) {
    return (
      <div>
        <Text type="secondary">No alpha scores available</Text>
      </div>
    );
  }

  const columns = [
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
      sorter: (a: AlphaFactorScore, b: AlphaFactorScore) => a.symbol.localeCompare(b.symbol),
      render: (sym: string, row: AlphaFactorScore) => (
        <Text strong style={{ cursor: onRowClick ? 'pointer' : 'default' }}>
          {sym} {row.direction > 0 ? <Tag color="green" style={{ fontSize: 10 }}>L</Tag> : row.direction < 0 ? <Tag color="red" style={{ fontSize: 10 }}>S</Tag> : null}
        </Text>
      ),
    },
    {
      title: <Tooltip title="Weighted composite of all 7 alpha factors">Composite</Tooltip>,
      dataIndex: 'composite_score',
      key: 'composite',
      sorter: (a: AlphaFactorScore, b: AlphaFactorScore) => a.composite_score - b.composite_score,
      defaultSortOrder: 'descend' as const,
      render: (val: number, row: AlphaFactorScore) => (
        <span style={nearThresholdStyle(val, row.threshold)}>
          <Text type={row.passed_threshold ? 'success' : 'secondary'}>{val.toFixed(3)}</Text>
        </span>
      ),
    },
    {
      title: 'ML',
      key: 'ml',
      render: (_: unknown, row: AlphaFactorScore) => row.factors.ml.toFixed(2),
    },
    {
      title: 'Breakout',
      key: 'breakout',
      render: (_: unknown, row: AlphaFactorScore) => row.factors.breakout.toFixed(2),
    },
    {
      title: 'Inst.',
      key: 'institutional',
      render: (_: unknown, row: AlphaFactorScore) => row.factors.institutional.toFixed(2),
    },
    {
      title: 'Mom.',
      key: 'momentum',
      render: (_: unknown, row: AlphaFactorScore) => row.factors.momentum.toFixed(2),
    },
    {
      title: 'Regime',
      key: 'regime',
      render: (_: unknown, row: AlphaFactorScore) => row.factors.regime.toFixed(2),
    },
    {
      title: <Tooltip title="Distance from MIN_COMPOSITE threshold">Dist</Tooltip>,
      dataIndex: 'distance_to_threshold',
      key: 'distance',
      render: (val: number) => (
        <Text type={val >= 0 ? 'success' : 'danger'}>{val >= 0 ? '+' : ''}{val.toFixed(3)}</Text>
      ),
    },
    {
      title: 'Fitness',
      key: 'fitness',
      render: (_: unknown, row: AlphaFactorScore) => (
        <Tag color={row.passed_fitness ? 'green' : 'red'}>{row.symbol_fitness.toFixed(2)}</Tag>
      ),
    },
  ];

  return (
    <Table
      dataSource={data.map((d) => ({ key: d.symbol, ...d }))}
      columns={columns}
      size="small"
      pagination={{ pageSize: 15, showSizeChanger: false }}
      onRow={(record) => ({
        onClick: () => onRowClick?.(record.symbol),
        style: { cursor: onRowClick ? 'pointer' : 'default' },
      })}
    />
  );
};

export default AlphaScoreTable;
