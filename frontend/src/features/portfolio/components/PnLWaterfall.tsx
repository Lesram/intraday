import { useEffect, useRef, useMemo } from 'react';
import { Card, Typography } from 'antd';
import { usePortfolioStore } from '@/store/portfolioStore';

const { Text } = Typography;

const PnLWaterfall = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const portfolio = usePortfolioStore((state) => state.portfolio);

  const data = useMemo(() => {
    const raw = portfolio?.positions ?? [];
    return raw
      .map((p) => ({
        symbol: p.symbol,
        pnl: p.unrealizedPnL,
      }))
      .sort((a, b) => b.pnl - a.pnl);
  }, [portfolio]);

  const equity = portfolio?.totalEquity ?? 0;
  const totalPnl = data.reduce((sum, p) => sum + p.pnl, 0);
  const startingEquity = equity - totalPnl;

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
    const padding = { top: 20, right: 20, bottom: 40, left: 60 };
    const chartW = w - padding.left - padding.right;
    const chartH = h - padding.top - padding.bottom;

    // Build waterfall segments: [starting, ...positions, ending]
    const segments = [
      { label: 'Start', value: startingEquity, type: 'start' as const },
      ...data.map((d) => ({ label: d.symbol, value: d.pnl, type: 'delta' as const })),
      { label: 'Current', value: equity, type: 'end' as const },
    ];

    const numBars = segments.length;
    const barWidth = Math.min(chartW / numBars * 0.7, 40);
    const gap = (chartW - barWidth * numBars) / (numBars + 1);

    // Compute running totals for the waterfall
    const runningTotals: number[] = [];
    let running = startingEquity;
    for (const seg of segments) {
      if (seg.type === 'start') {
        runningTotals.push(0);
      } else if (seg.type === 'delta') {
        runningTotals.push(running);
        running += seg.value;
      } else {
        runningTotals.push(0);
      }
    }

    // Determine scale
    const allValues = [startingEquity, equity, ...runningTotals.map((rt, i) =>
      rt + (segments[i].type === 'delta' ? segments[i].value : 0),
    )];
    const maxVal = Math.max(...allValues, equity) * 1.05;
    const minVal = Math.min(...allValues.filter((v) => v > 0), startingEquity) * 0.95;
    const range = maxVal - minVal || 1;

    const yScale = (val: number) => padding.top + chartH * (1 - (val - minVal) / range);

    ctx.clearRect(0, 0, w, h);

    // Draw bars
    segments.forEach((seg, i) => {
      const x = padding.left + gap + i * (barWidth + gap);

      if (seg.type === 'start' || seg.type === 'end') {
        const barH = chartH * (seg.value - minVal) / range;
        const y = yScale(seg.value);
        ctx.fillStyle = '#1890ff';
        ctx.fillRect(x, y, barWidth, barH);
      } else {
        const base = runningTotals[i];
        const top = base + seg.value;
        const y1 = yScale(Math.max(base, top));
        const y2 = yScale(Math.min(base, top));
        ctx.fillStyle = seg.value >= 0 ? '#52c41a' : '#ff4d4f';
        ctx.fillRect(x, y1, barWidth, y2 - y1);
      }

      // Label
      ctx.fillStyle = '#666';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.save();
      ctx.translate(x + barWidth / 2, h - padding.bottom + 12);
      ctx.rotate(-Math.PI / 6);
      ctx.fillText(seg.label, 0, 0);
      ctx.restore();
    });

    // Y-axis labels
    ctx.fillStyle = '#999';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'right';
    const ticks = 5;
    for (let i = 0; i <= ticks; i++) {
      const val = minVal + (range * i) / ticks;
      const y = yScale(val);
      ctx.fillText(`$${(val / 1000).toFixed(1)}k`, padding.left - 5, y + 3);
      ctx.strokeStyle = '#f0f0f0';
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(w - padding.right, y);
      ctx.stroke();
    }
  }, [data, startingEquity, equity]);

  if (data.length === 0) {
    return (
      <Card title="P&L Waterfall" size="small">
        <Text type="secondary">No positions to display</Text>
      </Card>
    );
  }

  return (
    <Card title="P&L Waterfall" size="small">
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: 250 }}
      />
    </Card>
  );
};

export default PnLWaterfall;
