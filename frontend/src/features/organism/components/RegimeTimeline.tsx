import { useEffect, useRef, useMemo } from 'react';
import { Card, Typography } from 'antd';
import type { RegimeTimelineEntry } from '../organismApi';

const { Text } = Typography;

const REGIME_COLORS: Record<string, string> = {
  trending_up: '#52c41a',
  trending: '#73d13d',
  normal: '#1890ff',
  trending_down: '#faad14',
  chop: '#fa8c16',
  high_vol: '#ff7a45',
  stress: '#ff4d4f',
  crisis: '#cf1322',
};

const RegimeTimeline = ({ data }: { data: RegimeTimelineEntry[] }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const segments = useMemo(() => {
    if (data.length === 0) return [];
    // Group consecutive same-regime entries
    const grouped: { regime: string; startIdx: number; endIdx: number }[] = [];
    let current = { regime: data[0].regime, startIdx: 0, endIdx: 0 };
    for (let i = 1; i < data.length; i++) {
      if (data[i].regime === current.regime) {
        current.endIdx = i;
      } else {
        grouped.push({ ...current });
        current = { regime: data[i].regime, startIdx: i, endIdx: i };
      }
    }
    grouped.push(current);
    return grouped;
  }, [data]);

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
    const pad = { left: 10, right: 10, top: 10, bottom: 25 };
    const barH = h - pad.top - pad.bottom;
    const barW = w - pad.left - pad.right;
    const n = data.length;

    ctx.clearRect(0, 0, w, h);

    // Draw segments
    segments.forEach((seg) => {
      const x1 = pad.left + (seg.startIdx / n) * barW;
      const x2 = pad.left + ((seg.endIdx + 1) / n) * barW;
      ctx.fillStyle = REGIME_COLORS[seg.regime] ?? '#999';
      ctx.fillRect(x1, pad.top, x2 - x1, barH);

      // Label if wide enough
      const segW = x2 - x1;
      if (segW > 40) {
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 10px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(seg.regime.replace('_', ' '), (x1 + x2) / 2, pad.top + barH / 2 + 4);
      }
    });

    // Time labels at start and end
    ctx.fillStyle = '#999';
    ctx.font = '9px sans-serif';
    ctx.textAlign = 'left';
    if (data.length > 0) {
      const startTime = new Date(data[0].timestamp);
      if (!isNaN(startTime.getTime())) {
        ctx.fillText(startTime.toLocaleTimeString(), pad.left, h - 5);
      }
    }
    ctx.textAlign = 'right';
    if (data.length > 1) {
      const endTime = new Date(data[data.length - 1].timestamp);
      if (!isNaN(endTime.getTime())) {
        ctx.fillText(endTime.toLocaleTimeString(), w - pad.right, h - 5);
      }
    }
  }, [data, segments]);

  if (data.length === 0) {
    return (
      <Card title="Regime Timeline" size="small">
        <Text type="secondary">No regime history yet</Text>
      </Card>
    );
  }

  // Legend
  const activeRegimes = [...new Set(data.map((d) => d.regime))];

  return (
    <Card title="Regime Timeline" size="small">
      <canvas ref={canvasRef} style={{ width: '100%', height: 50 }} />
      <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {activeRegimes.map((r) => (
          <span key={r} style={{ fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                backgroundColor: REGIME_COLORS[r] ?? '#999',
                display: 'inline-block',
              }}
            />
            {r.replace('_', ' ')}
          </span>
        ))}
      </div>
    </Card>
  );
};

export default RegimeTimeline;
