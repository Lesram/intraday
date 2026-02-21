import { useMemo } from 'react';
import { Card, Tooltip, Typography } from 'antd';
import { usePortfolioStore } from '@/store/portfolioStore';

const { Text } = Typography;

const pnlColor = (pnl: number): string => {
  if (pnl >= 5) return '#237804';
  if (pnl >= 2) return '#389e0d';
  if (pnl >= 0.5) return '#52c41a';
  if (pnl >= 0) return '#b7eb8f';
  if (pnl >= -0.5) return '#ffa39e';
  if (pnl >= -2) return '#ff4d4f';
  if (pnl >= -5) return '#cf1322';
  return '#820014';
};

const PositionHeatmap = () => {
  const portfolio = usePortfolioStore((state) => state.portfolio);

  const positions = useMemo(() => {
    const raw = portfolio?.positions ?? [];
    return raw
      .map((p) => ({
        symbol: p.symbol,
        qty: p.quantity,
        avgEntry: p.averagePrice,
        currentPrice: p.currentPrice,
        marketValue: p.marketValue,
        unrealizedPl: p.unrealizedPnL,
        pnlPct: p.unrealizedPnLPercent,
      }))
      .sort((a, b) => b.pnlPct - a.pnlPct);
  }, [portfolio]);

  if (positions.length === 0) {
    return (
      <Card title="Position Heatmap" size="small">
        <Text type="secondary">No open positions</Text>
      </Card>
    );
  }

  return (
    <Card title="Position Heatmap" size="small">
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {positions.map((p) => (
          <Tooltip
            key={p.symbol}
            title={
              <div>
                <div><strong>{p.symbol}</strong></div>
                <div>Qty: {p.qty}</div>
                <div>Entry: ${p.avgEntry.toFixed(2)}</div>
                <div>Current: ${p.currentPrice.toFixed(2)}</div>
                <div>Value: ${p.marketValue.toFixed(0)}</div>
                <div>P&L: ${p.unrealizedPl.toFixed(2)} ({p.pnlPct.toFixed(2)}%)</div>
              </div>
            }
          >
            <div
              style={{
                backgroundColor: pnlColor(p.pnlPct),
                color: '#fff',
                padding: '8px 12px',
                borderRadius: 6,
                minWidth: 80,
                textAlign: 'center',
                cursor: 'default',
                fontWeight: 600,
                fontSize: 13,
              }}
            >
              <div>{p.symbol}</div>
              <div style={{ fontSize: 11, opacity: 0.9 }}>
                {p.pnlPct >= 0 ? '+' : ''}{p.pnlPct.toFixed(1)}%
              </div>
            </div>
          </Tooltip>
        ))}
      </div>
    </Card>
  );
};

export default PositionHeatmap;
