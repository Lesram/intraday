import { Card, Table, Tag, Progress, Statistic, Row, Col, Badge, Empty, Typography } from 'antd';
import { RadarChartOutlined, ClockCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { ScannerStatus, ScannedStock } from './organismApi';

const { Text } = Typography;

interface ScannerPanelProps {
  scanner: ScannerStatus | null;
  loading?: boolean;
}

const tensionColor = (score: number): string => {
  if (score >= 0.7) return '#52c41a';  // green — high tension
  if (score >= 0.5) return '#1890ff';  // blue — medium
  if (score >= 0.3) return '#faad14';  // orange — low
  return '#8c8c8c';                     // gray — minimal
};

const sourceTag = (source: string) => {
  const colorMap: Record<string, string> = {
    most_actives: 'blue',
    movers_up: 'green',
    movers_down: 'red',
  };
  return <Tag color={colorMap[source] || 'default'}>{source.replace('_', ' ')}</Tag>;
};

const columns: ColumnsType<ScannedStock & { key: string }> = [
  {
    title: 'Symbol',
    dataIndex: 'symbol',
    key: 'symbol',
    width: 90,
    render: (sym: string) => <Text strong>{sym}</Text>,
  },
  {
    title: 'Source',
    dataIndex: 'source',
    key: 'source',
    width: 120,
    render: sourceTag,
  },
  {
    title: 'Price',
    dataIndex: 'price',
    key: 'price',
    width: 90,
    align: 'right',
    render: (v: number) => `$${v.toFixed(2)}`,
  },
  {
    title: 'Volume',
    dataIndex: 'volume',
    key: 'volume',
    width: 110,
    align: 'right',
    render: (v: number) => {
      if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
      if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
      return v.toString();
    },
    sorter: (a, b) => a.volume - b.volume,
  },
  {
    title: 'Change %',
    dataIndex: 'change_pct',
    key: 'change_pct',
    width: 90,
    align: 'right',
    render: (v: number) => (
      <Text type={v >= 0 ? 'success' : 'danger'}>{(v * 100).toFixed(2)}%</Text>
    ),
    sorter: (a, b) => a.change_pct - b.change_pct,
  },
  {
    title: 'Tension',
    dataIndex: 'tension_score',
    key: 'tension_score',
    width: 150,
    sorter: (a, b) => a.tension_score - b.tension_score,
    defaultSortOrder: 'descend',
    render: (score: number) => (
      <Progress
        percent={Math.round(score * 100)}
        size="small"
        strokeColor={tensionColor(score)}
        format={(pct) => `${pct}%`}
      />
    ),
  },
];

const ScannerPanel = ({ scanner, loading }: ScannerPanelProps) => {
  if (!scanner || !scanner.enabled) {
    return (
      <Card title={<><RadarChartOutlined /> Market Scanner</>}>
        <Empty description="Market Scanner is not enabled. Set SCANNER_ENABLED=true in .env" />
      </Card>
    );
  }

  const lastScan = scanner.last_scan_time
    ? new Date(scanner.last_scan_time).toLocaleTimeString()
    : 'Never';

  const dataSource = scanner.candidates.map((s) => ({ ...s, key: s.symbol }));

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="Status"
              value={scanner.enabled ? 'Active' : 'Off'}
              prefix={<Badge status={scanner.enabled ? 'processing' : 'default'} />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Scans Run" value={scanner.scan_count} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic
              title="Last Scan"
              value={lastScan}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="Candidates" value={scanner.candidate_count} />
          </Card>
        </Col>
      </Row>

      <Card
        title={`Discovered Stocks (${dataSource.length})`}
        size="small"
      >
        <Table
          dataSource={dataSource}
          columns={columns}
          pagination={{ pageSize: 15, showSizeChanger: true, pageSizeOptions: ['10', '15', '30', '50'] }}
          size="small"
          loading={loading}
          scroll={{ y: 400 }}
          locale={{ emptyText: 'No stocks discovered yet — scanner runs every ~60s' }}
        />
      </Card>
    </div>
  );
};

export default ScannerPanel;
