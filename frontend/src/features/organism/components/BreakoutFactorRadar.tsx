import { useEffect, useRef } from 'react';
import { Card, Tag, Typography } from 'antd';
import type { BreakoutFactorScore } from '../organismApi';

const { Text } = Typography;

const FACTORS = ['squeeze', 'volume', 'contraction', 'rs', 'pivot', 'flow'] as const;
const LABELS = ['Squeeze', 'Volume', 'Contract.', 'Rel. Str.', 'Pivot', 'Flow'];

const BreakoutFactorRadar = ({ data, threshold }: { data: BreakoutFactorScore | null; threshold?: number }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const size = 220;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const cx = size / 2;
    const cy = size / 2;
    const r = size / 2 - 30;
    const n = FACTORS.length;
    const step = (2 * Math.PI) / n;

    ctx.clearRect(0, 0, size, size);

    // Grid rings
    for (let ring = 0.25; ring <= 1; ring += 0.25) {
      ctx.beginPath();
      for (let i = 0; i <= n; i++) {
        const angle = i * step - Math.PI / 2;
        const x = cx + Math.cos(angle) * r * ring;
        const y = cy + Math.sin(angle) * r * ring;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = '#e8e8e8';
      ctx.lineWidth = 0.5;
      ctx.stroke();
    }

    // Axis lines + labels
    for (let i = 0; i < n; i++) {
      const angle = i * step - Math.PI / 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(angle) * r, cy + Math.sin(angle) * r);
      ctx.strokeStyle = '#d9d9d9';
      ctx.lineWidth = 0.5;
      ctx.stroke();

      const lx = cx + Math.cos(angle) * (r + 16);
      const ly = cy + Math.sin(angle) * (r + 16);
      ctx.fillStyle = '#666';
      ctx.font = '9px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(LABELS[i], lx, ly);
    }

    // Threshold
    if (threshold) {
      ctx.beginPath();
      ctx.setLineDash([4, 3]);
      for (let i = 0; i <= n; i++) {
        const angle = (i % n) * step - Math.PI / 2;
        const x = cx + Math.cos(angle) * r * threshold;
        const y = cy + Math.sin(angle) * r * threshold;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = '#ff4d4f';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Data polygon
    const values = FACTORS.map((f) => Math.min(data.factors[f], 1));
    ctx.beginPath();
    for (let i = 0; i <= n; i++) {
      const angle = (i % n) * step - Math.PI / 2;
      const v = values[i % n];
      const x = cx + Math.cos(angle) * r * v;
      const y = cy + Math.sin(angle) * r * v;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.fillStyle = 'rgba(114, 46, 209, 0.2)';
    ctx.fill();
    ctx.strokeStyle = '#722ed1';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Data points
    for (let i = 0; i < n; i++) {
      const angle = i * step - Math.PI / 2;
      const v = values[i];
      const x = cx + Math.cos(angle) * r * v;
      const y = cy + Math.sin(angle) * r * v;
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, 2 * Math.PI);
      ctx.fillStyle = '#722ed1';
      ctx.fill();
    }
  }, [data, threshold]);

  if (!data) {
    return (
      <Card title="Breakout Factors" size="small">
        <Text type="secondary">Select a symbol to see breakout factors</Text>
      </Card>
    );
  }

  return (
    <Card title={`Breakout Factors: ${data.symbol}`} size="small">
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <canvas ref={canvasRef} style={{ width: 220, height: 220 }} />
      </div>
      <div style={{ textAlign: 'center', marginTop: 4 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          Composite: {data.composite_score.toFixed(3)}
        </Text>
        {data.squeeze_fired && <Tag color="orange" style={{ marginLeft: 8, fontSize: 10 }}>Squeeze Fired</Tag>}
      </div>
    </Card>
  );
};

export default BreakoutFactorRadar;
