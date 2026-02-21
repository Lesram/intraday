import { useEffect, useRef, useMemo } from 'react';
import { Card, Col, Row, Table, Tag, Typography } from 'antd';
import type { SectorExposure, ConfidenceBin } from '../organismApi';

const { Text } = Typography;

// ── Sector Exposure Table ──────────────────────────────────────────

const SectorExposureTable = ({ data }: { data: SectorExposure[] }) => {
  const columns = [
    {
      title: 'Sector',
      dataIndex: 'sector',
      key: 'sector',
      render: (val: string) => <Tag>{val}</Tag>,
    },
    { title: 'Positions', dataIndex: 'count', key: 'count' },
    {
      title: 'Symbols',
      dataIndex: 'symbols',
      key: 'symbols',
      render: (syms: string[]) => syms.join(', '),
    },
    {
      title: 'Value',
      dataIndex: 'total_value',
      key: 'total_value',
      render: (val: number) => `$${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
    },
  ];

  return (
    <Card title="Sector Exposure" size="small">
      {data.length === 0 ? (
        <Text type="secondary">No sector data available</Text>
      ) : (
        <Table
          dataSource={data.map((d, i) => ({ key: i, ...d }))}
          columns={columns}
          pagination={false}
          size="small"
        />
      )}
    </Card>
  );
};

// ── Confidence Distribution Chart ─────────────────────────────────

const ConfidenceHistogram = ({ data }: { data: ConfidenceBin[] }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const displayW = canvas.clientWidth;
    const displayH = canvas.clientHeight;
    canvas.width = displayW * dpr;
    canvas.height = displayH * dpr;
    ctx.scale(dpr, dpr);

    const w = displayW;
    const h = displayH;
    const pad = { top: 15, right: 15, bottom: 30, left: 40 };
    const chartW = w - pad.left - pad.right;
    const chartH = h - pad.top - pad.bottom;

    const maxTotal = Math.max(...data.map((d) => d.total), 1);
    const barWidth = chartW / data.length * 0.7;
    const gap = chartW / data.length * 0.3;

    ctx.clearRect(0, 0, w, h);

    data.forEach((d, i) => {
      const x = pad.left + i * (barWidth + gap) + gap / 2;
      const accuracy = d.total > 0 ? d.correct / d.total : 0;

      // Total bar
      const totalH = (d.total / maxTotal) * chartH;
      ctx.fillStyle = '#e6e6e6';
      ctx.fillRect(x, pad.top + chartH - totalH, barWidth, totalH);

      // Correct bar overlaid
      const correctH = (d.correct / maxTotal) * chartH;
      ctx.fillStyle = accuracy >= 0.5 ? '#52c41a' : '#ff4d4f';
      ctx.fillRect(x, pad.top + chartH - correctH, barWidth, correctH);

      // Label
      ctx.fillStyle = '#666';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(d.bin, x + barWidth / 2, h - pad.bottom + 15);

      // Accuracy label on top
      if (d.total > 0) {
        ctx.fillStyle = '#333';
        ctx.font = '9px sans-serif';
        ctx.fillText(
          `${(accuracy * 100).toFixed(0)}%`,
          x + barWidth / 2,
          pad.top + chartH - totalH - 3,
        );
      }
    });

    // Y-axis
    ctx.fillStyle = '#999';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'right';
    for (let i = 0; i <= 4; i++) {
      const val = (maxTotal * i) / 4;
      const y = pad.top + chartH * (1 - i / 4);
      ctx.fillText(String(Math.round(val)), pad.left - 5, y + 3);
    }
  }, [data]);

  return (
    <Card title="ML Confidence Distribution" size="small">
      {data.length === 0 || data.every((d) => d.total === 0) ? (
        <Text type="secondary">No confidence data yet — accumulates from trades</Text>
      ) : (
        <canvas ref={canvasRef} style={{ width: '100%', height: 180 }} />
      )}
    </Card>
  );
};

// ── Regime Kelly Stats ────────────────────────────────────────────

const RegimeKellyTable = ({ data }: { data: Record<string, Record<string, number>> }) => {
  const rows = useMemo(() => {
    return Object.entries(data).map(([regime, stats]) => {
      const total = (stats.wins ?? 0) + (stats.losses ?? 0);
      const winRate = total > 0 ? (stats.wins ?? 0) / total : 0;
      return {
        key: regime,
        regime,
        wins: stats.wins ?? 0,
        losses: stats.losses ?? 0,
        winRate,
        totalPnl: stats.total_pnl ?? 0,
      };
    });
  }, [data]);

  if (rows.length === 0) {
    return (
      <Card title="Regime Kelly Stats" size="small">
        <Text type="secondary">No regime-level trade data yet</Text>
      </Card>
    );
  }

  return (
    <Card title="Regime Performance" size="small">
      <Table
        dataSource={rows}
        columns={[
          { title: 'Regime', dataIndex: 'regime', key: 'regime', render: (v: string) => <Tag>{v}</Tag> },
          { title: 'Wins', dataIndex: 'wins', key: 'wins' },
          { title: 'Losses', dataIndex: 'losses', key: 'losses' },
          {
            title: 'Win Rate',
            dataIndex: 'winRate',
            key: 'winRate',
            render: (v: number) => (
              <Text type={v >= 0.5 ? 'success' : 'danger'}>{(v * 100).toFixed(1)}%</Text>
            ),
          },
          {
            title: 'Total P&L',
            dataIndex: 'totalPnl',
            key: 'totalPnl',
            render: (v: number) => (
              <Text type={v >= 0 ? 'success' : 'danger'}>${v.toFixed(2)}</Text>
            ),
          },
        ]}
        pagination={false}
        size="small"
      />
    </Card>
  );
};

// ── Combined Attribution Panel ────────────────────────────────────

const AttributionPanel = ({
  sectorExposure,
  confidenceDist,
  regimeKellyStats,
}: {
  sectorExposure: SectorExposure[];
  confidenceDist: ConfidenceBin[];
  regimeKellyStats: Record<string, Record<string, number>>;
}) => {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} lg={12}>
        <SectorExposureTable data={sectorExposure} />
      </Col>
      <Col xs={24} lg={12}>
        <ConfidenceHistogram data={confidenceDist} />
      </Col>
      <Col xs={24}>
        <RegimeKellyTable data={regimeKellyStats} />
      </Col>
    </Row>
  );
};

export default AttributionPanel;
export { SectorExposureTable, ConfidenceHistogram, RegimeKellyTable };
