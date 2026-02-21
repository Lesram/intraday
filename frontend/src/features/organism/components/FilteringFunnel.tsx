import { useEffect, useRef } from 'react';
import { Card, Typography } from 'antd';
import type { FilteringSummary } from '../organismApi';

const { Text } = Typography;

const FilteringFunnel = ({ data }: { data: FilteringSummary | null }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
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
    const pad = { left: 10, right: 10, top: 8, bottom: 20 };
    const barH = 22;
    const gap = 3;

    const stages = [
      { label: 'Universe', value: data.total_universe, color: '#bae7ff' },
      { label: 'Alpha Scored', value: data.alpha_scored, color: '#91d5ff' },
      { label: 'Above Threshold', value: data.above_alpha_threshold, color: '#69c0ff' },
      { label: 'Breakout Scored', value: data.breakout_scored, color: '#40a9ff' },
      { label: 'Kelly Sized', value: data.kelly_sized, color: '#1890ff' },
      { label: 'Orders', value: data.orders_submitted, color: '#096dd9' },
    ];

    ctx.clearRect(0, 0, w, h);

    const maxVal = Math.max(data.total_universe, 1);
    const barArea = w - pad.left - pad.right;

    stages.forEach((stage, i) => {
      const y = pad.top + i * (barH + gap);
      const barW = Math.max((stage.value / maxVal) * barArea, 2);

      ctx.fillStyle = stage.color;
      ctx.fillRect(pad.left, y, barW, barH);

      // Label
      ctx.fillStyle = stage.value > maxVal * 0.3 ? '#fff' : '#333';
      ctx.font = 'bold 11px sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      const labelX = stage.value > maxVal * 0.3 ? pad.left + 6 : pad.left + barW + 4;
      ctx.fillText(`${stage.label}: ${stage.value}`, labelX, y + barH / 2);
    });
  }, [data]);

  if (!data) {
    return (
      <Card title="Filtering Funnel" size="small">
        <Text type="secondary">No filtering data yet</Text>
      </Card>
    );
  }

  return (
    <Card title="Filtering Funnel" size="small">
      <canvas ref={canvasRef} style={{ width: '100%', height: 160 }} />
    </Card>
  );
};

export default FilteringFunnel;
