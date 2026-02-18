import { Card, Table, Tag, Progress, Statistic, Row, Col, Typography, Tooltip } from 'antd';
import { GlobalOutlined, SwapOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { UniverseStatus, SymbolFitness } from './organismApi';

const { Text } = Typography;

interface UniversePanelProps {
  universe: UniverseStatus | null;
  loading?: boolean;
}

const fitnessColor = (fitness: number): string => {
  if (fitness >= 0.7) return '#52c41a';
  if (fitness >= 0.5) return '#1890ff';
  if (fitness >= 0.35) return '#faad14';
  return '#f5222d';
};

const columns = (activeSet: Set<string>): ColumnsType<SymbolFitness & { key: string }> => [
  {
    title: 'Symbol',
    dataIndex: 'symbol',
    key: 'symbol',
    width: 90,
    render: (sym: string) => (
      <Text strong>
        {sym}{' '}
        {activeSet.has(sym) ? (
          <Tag color="green" style={{ fontSize: 10, padding: '0 4px' }}>active</Tag>
        ) : (
          <Tag color="default" style={{ fontSize: 10, padding: '0 4px' }}>pool</Tag>
        )}
      </Text>
    ),
    filters: [
      { text: 'Active', value: 'active' },
      { text: 'Pool', value: 'pool' },
    ],
    onFilter: (value, record) =>
      value === 'active' ? activeSet.has(record.symbol) : !activeSet.has(record.symbol),
  },
  {
    title: 'Fitness',
    dataIndex: 'fitness',
    key: 'fitness',
    width: 140,
    sorter: (a, b) => a.fitness - b.fitness,
    defaultSortOrder: 'descend',
    render: (f: number) => (
      <Tooltip title={f.toFixed(4)}>
        <Progress
          percent={Math.round(f * 100)}
          size="small"
          strokeColor={fitnessColor(f)}
          format={(pct) => `${pct}%`}
        />
      </Tooltip>
    ),
  },
  {
    title: 'Trades',
    dataIndex: 'total_trades',
    key: 'total_trades',
    width: 70,
    align: 'right',
    sorter: (a, b) => a.total_trades - b.total_trades,
  },
  {
    title: 'Win Rate',
    dataIndex: 'win_rate',
    key: 'win_rate',
    width: 90,
    align: 'right',
    render: (v: number) => (
      <Text type={v >= 0.5 ? 'success' : v > 0 ? 'warning' : 'secondary'}>
        {(v * 100).toFixed(1)}%
      </Text>
    ),
    sorter: (a, b) => a.win_rate - b.win_rate,
  },
  {
    title: 'Avg PnL',
    dataIndex: 'avg_pnl',
    key: 'avg_pnl',
    width: 90,
    align: 'right',
    render: (v: number) => (
      <Text type={v >= 0 ? 'success' : 'danger'}>${v.toFixed(2)}</Text>
    ),
    sorter: (a, b) => a.avg_pnl - b.avg_pnl,
  },
  {
    title: 'Vol Quality',
    dataIndex: 'avg_volume_quality',
    key: 'avg_volume_quality',
    width: 90,
    align: 'right',
    render: (v: number) => `${(v * 100).toFixed(0)}%`,
  },
];

const UniversePanel = ({ universe, loading }: UniversePanelProps) => {
  if (!universe || universe.universe_size === 0) {
    return (
      <Card title={<><GlobalOutlined /> Universe</>}>
        <Text type="secondary">Universe data not available — engine may not be running.</Text>
      </Card>
    );
  }

  const activeSet = new Set(universe.active_symbols);
  const capacityPct = Math.round(
    (universe.universe_size / (universe.config?.max_universe || 80)) * 100
  );

  const dataSource = universe.fitness_table.map((f) => ({ ...f, key: f.symbol }));

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Active Symbols" value={universe.universe_size} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Capacity" value={`${capacityPct}%`} />
            <Progress
              percent={capacityPct}
              size="small"
              showInfo={false}
              strokeColor={capacityPct > 90 ? '#f5222d' : '#1890ff'}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="Rotations"
              value={universe.rotation_count}
              prefix={<SwapOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Scanner Candidates" value={universe.scanner_candidates.length} />
          </Card>
        </Col>
      </Row>

      <Card
        title={`Fitness Table (${dataSource.length} symbols tracked)`}
        size="small"
      >
        <Table
          dataSource={dataSource}
          columns={columns(activeSet)}
          pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: ['10', '20', '40', '80'] }}
          size="small"
          loading={loading}
          scroll={{ y: 450 }}
        />
      </Card>
    </div>
  );
};

export default UniversePanel;
