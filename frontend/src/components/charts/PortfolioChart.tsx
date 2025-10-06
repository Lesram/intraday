/**
 * Portfolio Performance Chart
 * Displays portfolio value over time with interactive chart
 * Note: Using placeholder until charting library is installed
 */

import { useMemo } from 'react';
import { Spin } from 'antd';
import { colors } from '@/styles/theme';
import { formatCurrency } from '@/utils/formatters';

interface PortfolioChartProps {
  data?: Array<{
    timestamp: string;
    totalEquity: number;
  }>;
  loading?: boolean;
}

export const PortfolioChart: React.FC<PortfolioChartProps> = ({ 
  data = [], 
  loading = false 
}) => {
  // Calculate min/max for scale
  const { minValue, maxValue, range } = useMemo(() => {
    if (!data || data.length === 0) {
      return { minValue: 0, maxValue: 100000, range: 100000 };
    }
    
    const values = data.map(d => d.totalEquity);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = (max - min) * 0.1 || 10000; // 10% padding or $10k minimum
    
    return {
      minValue: min - padding,
      maxValue: max + padding,
      range: max - min + 2 * padding,
    };
  }, [data]);

  // Loading state
  if (loading) {
    return (
      <div style={{
        height: '300px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <Spin size="large" />
      </div>
    );
  }

  // Empty state
  if (!data || data.length === 0) {
    return (
      <div style={{
        height: '300px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        color: colors.text.tertiary,
      }}>
        <p style={{ fontSize: '16px', marginBottom: '8px' }}>
          No performance data available
        </p>
        <p style={{ fontSize: '14px' }}>
          Chart will appear as trading activity occurs
        </p>
      </div>
    );
  }

  // Simple SVG line chart
  const width = 800;
  const height = 300;
  const padding = { top: 20, right: 20, bottom: 40, left: 60 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Generate SVG path
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * chartWidth + padding.left;
    const y = height - padding.bottom - ((d.totalEquity - minValue) / range) * chartHeight;
    return { x, y, data: d };
  });

  const pathData = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x},${p.y}`)
    .join(' ');

  // Generate grid lines (horizontal)
  const gridLines = [0, 0.25, 0.5, 0.75, 1].map(ratio => {
    const y = height - padding.bottom - ratio * chartHeight;
    const value = minValue + ratio * range;
    return { y, value };
  });

  return (
    <div style={{ height: '300px', width: '100%', position: 'relative' }}>
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Grid lines */}
        {gridLines.map((line, i) => (
          <g key={i}>
            <line
              x1={padding.left}
              y1={line.y}
              x2={width - padding.right}
              y2={line.y}
              stroke={colors.backgrounds.border}
              strokeWidth={1}
              strokeDasharray="2,2"
              opacity={0.3}
            />
            <text
              x={padding.left - 10}
              y={line.y + 4}
              fill={colors.text.tertiary}
              fontSize={12}
              textAnchor="end"
            >
              {formatCurrency(line.value)}
            </text>
          </g>
        ))}

        {/* Chart line */}
        <path
          d={pathData}
          fill="none"
          stroke={colors.brand.primary}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Data points */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={3}
            fill={colors.brand.primary}
            stroke={colors.backgrounds.primary}
            strokeWidth={2}
          >
            <title>
              {new Date(p.data.timestamp).toLocaleString()}: {formatCurrency(p.data.totalEquity)}
            </title>
          </circle>
        ))}

        {/* X-axis labels */}
        {points.filter((_, i) => i % Math.ceil(points.length / 6) === 0).map((p, i) => (
          <text
            key={i}
            x={p.x}
            y={height - padding.bottom + 20}
            fill={colors.text.tertiary}
            fontSize={12}
            textAnchor="middle"
          >
            {new Date(p.data.timestamp).toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </text>
        ))}
      </svg>
    </div>
  );
};

