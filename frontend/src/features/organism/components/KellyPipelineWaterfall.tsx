import { useEffect, useRef } from 'react';
import { Card, Typography } from 'antd';
import type { KellySizingStage } from '../organismApi';

const { Text } = Typography;

const KellyPipelineWaterfall = ({ data }: { data: KellySizingStage | null }) => {
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
    const pad = { left: 70, right: 10, top: 10, bottom: 10 };

    const stages = [
      { label: 'Kelly Raw', value: data.pipeline.kelly_raw },
      { label: 'Half Kelly', value: data.pipeline.kelly_half },
      { label: 'x DD Scale', value: data.pipeline.drawdown_scale },
      { label: 'x Vol Scale', value: data.pipeline.vol_scale },
      { label: 'x Regime', value: data.pipeline.regime_scale },
      { label: 'x Confidence', value: data.pipeline.confidence_scale },
      { label: 'x Breakout', value: data.pipeline.breakout_bonus },
      { label: 'Final Wt', value: data.pipeline.final_weight },
    ];

    const barH = Math.min(18, (h - pad.top - pad.bottom) / stages.length - 3);
    const gap = 3;
    const barArea = w - pad.left - pad.right;
    const maxVal = Math.max(...stages.map((s) => Math.abs(s.value)), 0.001);

    ctx.clearRect(0, 0, w, h);

    stages.forEach((stage, i) => {
      const y = pad.top + i * (barH + gap);
      const barW = Math.max((Math.abs(stage.value) / maxVal) * barArea * 0.8, 2);

      // Green for expanding multipliers (>1), red for contracting (<1)
      const isMultiplier = i >= 2 && i <= 6;
      const expanding = !isMultiplier || stage.value >= 1.0;
      ctx.fillStyle = expanding ? '#52c41a' : '#ff4d4f';
      ctx.fillRect(pad.left, y, barW, barH);

      // Label
      ctx.fillStyle = '#333';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillText(stage.label, pad.left - 4, y + barH / 2);

      // Value
      ctx.fillStyle = '#666';
      ctx.textAlign = 'left';
      ctx.fillText(stage.value.toFixed(4), pad.left + barW + 4, y + barH / 2);
    });
  }, [data]);

  if (!data) {
    return (
      <Card title="Kelly Pipeline" size="small">
        <Text type="secondary">Select a symbol to see Kelly pipeline</Text>
      </Card>
    );
  }

  return (
    <Card title={`Kelly Pipeline: ${data.symbol}`} size="small">
      <canvas ref={canvasRef} style={{ width: '100%', height: 180 }} />
      <div style={{ textAlign: 'center', marginTop: 4 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {data.shares} shares | ${data.notional.toFixed(0)} notional | Cap: {(data.position_cap * 100).toFixed(0)}%
        </Text>
      </div>
    </Card>
  );
};

export default KellyPipelineWaterfall;
