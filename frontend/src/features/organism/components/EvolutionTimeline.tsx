import { useEffect, useRef } from 'react';
import { Card, Typography } from 'antd';
import type { EvolutionSnapshot } from '../organismApi';

const { Text } = Typography;

const EvolutionTimeline = ({ data }: { data: EvolutionSnapshot[] }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.length < 2) return;
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
    const pad = { left: 50, right: 10, top: 10, bottom: 25 };

    // Draw equity line
    const equities = data.map((d) => d.equity).reverse();
    const drawdowns = data.map((d) => d.drawdown_pct * 100).reverse();
    const generations = data.map((d) => d.generation).reverse();

    const chartW = w - pad.left - pad.right;
    const chartH = (h - pad.top - pad.bottom) / 2;

    // Top chart: equity
    const eqMax = Math.max(...equities);
    const eqMin = Math.min(...equities);
    const eqRange = eqMax - eqMin || 1;

    ctx.clearRect(0, 0, w, h);

    ctx.beginPath();
    ctx.strokeStyle = '#1890ff';
    ctx.lineWidth = 1.5;
    equities.forEach((val, i) => {
      const x = pad.left + (i / (equities.length - 1)) * chartW;
      const y = pad.top + chartH - ((val - eqMin) / eqRange) * (chartH - 4);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Bottom chart: drawdown
    const ddMax = Math.max(...drawdowns, 1);
    const ddChartTop = pad.top + chartH + 10;

    ctx.beginPath();
    ctx.strokeStyle = '#ff4d4f';
    ctx.lineWidth = 1.5;
    drawdowns.forEach((val, i) => {
      const x = pad.left + (i / (drawdowns.length - 1)) * chartW;
      const y = ddChartTop + (val / ddMax) * (chartH - 14);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Generation markers
    let lastGen = -1;
    ctx.fillStyle = '#722ed1';
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'center';
    generations.forEach((gen, i) => {
      if (gen !== lastGen && gen > 0) {
        const x = pad.left + (i / (generations.length - 1)) * chartW;
        ctx.beginPath();
        ctx.setLineDash([2, 2]);
        ctx.strokeStyle = '#722ed1';
        ctx.lineWidth = 0.5;
        ctx.moveTo(x, pad.top);
        ctx.lineTo(x, h - pad.bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        lastGen = gen;
      }
    });

    // Axis labels
    ctx.fillStyle = '#999';
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText('Equity', pad.left - 4, pad.top + 10);
    ctx.fillText('DD %', pad.left - 4, ddChartTop + 10);
  }, [data]);

  if (data.length < 2) {
    return (
      <Card title="Evolution Timeline" size="small">
        <Text type="secondary">Insufficient evolution data — need at least 2 ticks</Text>
      </Card>
    );
  }

  const latest = data[0];
  return (
    <Card title="Evolution Timeline" size="small">
      <canvas ref={canvasRef} style={{ width: '100%', height: 160 }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          Generation: {latest.generation} | Equity: ${latest.equity.toFixed(0)} | DD: {(latest.drawdown_pct * 100).toFixed(2)}%
        </Text>
        <Text type="secondary" style={{ fontSize: 11 }}>{data.length} ticks</Text>
      </div>
    </Card>
  );
};

export default EvolutionTimeline;
