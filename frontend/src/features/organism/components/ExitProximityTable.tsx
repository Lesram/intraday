import { Progress, Table, Tag, Tooltip, Typography } from 'antd';
import type { ExitProximity } from '../organismApi';

const { Text } = Typography;

const exitColor = (distPct: number): string => {
  if (distPct < 15) return '#ff4d4f';
  if (distPct < 30) return '#faad14';
  return '#52c41a';
};

const ExitProximityTable = ({
  data,
  onRowClick,
}: {
  data: ExitProximity[];
  onRowClick?: (symbol: string) => void;
}) => {
  if (data.length === 0) {
    return <Text type="secondary">No open positions</Text>;
  }

  const columns = [
    {
      title: 'Symbol',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (sym: string, row: ExitProximity) => (
        <Text strong>
          {sym}{' '}
          <Tag color={row.pnl_pct >= 0 ? 'success' : 'error'} style={{ fontSize: 10 }}>
            {(row.pnl_pct * 100).toFixed(1)}%
          </Tag>
        </Text>
      ),
    },
    {
      title: 'Price',
      key: 'price',
      render: (_: unknown, row: ExitProximity) => `$${row.current_price.toFixed(2)}`,
    },
    {
      title: <Tooltip title="Distance to stop loss">Stop Loss</Tooltip>,
      key: 'stop_loss',
      render: (_: unknown, row: ExitProximity) => {
        const d = row.exits.stop_loss.distance_pct;
        return (
          <div>
            <Progress percent={Math.min(d, 100)} size="small" strokeColor={exitColor(d)} showInfo={false} style={{ width: 60 }} />
            <Text style={{ fontSize: 11, marginLeft: 4 }}>{d.toFixed(1)}%</Text>
          </div>
        );
      },
    },
    {
      title: <Tooltip title="Distance to take profit">Take Profit</Tooltip>,
      key: 'take_profit',
      render: (_: unknown, row: ExitProximity) => {
        const d = row.exits.take_profit.distance_pct;
        return (
          <div>
            <Progress percent={Math.min(d, 100)} size="small" strokeColor="#52c41a" showInfo={false} style={{ width: 60 }} />
            <Text style={{ fontSize: 11, marginLeft: 4 }}>{d.toFixed(1)}%</Text>
          </div>
        );
      },
    },
    {
      title: <Tooltip title="Trailing stop distance (active if ATR > 3x move)">Trail</Tooltip>,
      key: 'trail',
      render: (_: unknown, row: ExitProximity) => {
        const e = row.exits.trailing_stop;
        if (!e.active) return <Tag>Inactive</Tag>;
        return (
          <div>
            <Progress percent={Math.min(e.distance_pct, 100)} size="small" strokeColor={exitColor(e.distance_pct)} showInfo={false} style={{ width: 60 }} />
            <Text style={{ fontSize: 11, marginLeft: 4 }}>{e.distance_pct.toFixed(1)}%</Text>
          </div>
        );
      },
    },
    {
      title: <Tooltip title="Time-based exit progress">Time</Tooltip>,
      key: 'time',
      render: (_: unknown, row: ExitProximity) => {
        const { bars_held, max_bars } = row.exits.time;
        if (max_bars <= 0) return <Tag>No limit</Tag>;
        const pct = (bars_held / max_bars) * 100;
        return (
          <div>
            <Progress percent={pct} size="small" strokeColor={pct > 80 ? '#ff4d4f' : '#1890ff'} showInfo={false} style={{ width: 60 }} />
            <Text style={{ fontSize: 11, marginLeft: 4 }}>{bars_held}/{max_bars}</Text>
          </div>
        );
      },
    },
    {
      title: <Tooltip title="Nearest exit condition and its distance">Nearest</Tooltip>,
      key: 'nearest',
      render: (_: unknown, row: ExitProximity) => (
        <Tag color={row.nearest_exit_distance_pct < 15 ? 'error' : 'default'}>
          {row.nearest_exit.replace('_', ' ')} ({row.nearest_exit_distance_pct.toFixed(1)}%)
        </Tag>
      ),
    },
  ];

  return (
    <Table
      dataSource={data.map((d) => ({ key: d.symbol, ...d }))}
      columns={columns}
      size="small"
      pagination={false}
      onRow={(record) => ({
        onClick: () => onRowClick?.(record.symbol),
        style: { cursor: onRowClick ? 'pointer' : 'default' },
      })}
    />
  );
};

export default ExitProximityTable;
