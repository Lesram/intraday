/**
 * EquityCurveChart Component
 * 
 * Displays the equity curve from a backtest result showing portfolio value over time.
 * Uses lightweight-charts for consistent charting across the platform.
 * 
 * M-27 Fix: Consolidated from recharts to lightweight-charts to reduce bundle size
 * and maintain consistency with main trading charts.
 */

import React, { useEffect, useRef, useState } from 'react';
import { Card, Empty, Spin } from 'antd';
import { LineChartOutlined } from '@ant-design/icons';
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type LineData,
  type AreaData,
  LineSeries,
  AreaSeries,
} from 'lightweight-charts';
import dayjs from 'dayjs';
import type { EquityPoint } from '../../../types/backtest';

interface EquityCurveChartProps {
  equityCurve: EquityPoint[];
  initialCapital: number;
  loading?: boolean;
  height?: number;
}

interface TooltipData {
  date: string;
  equity: number;
  cash: number;
  positions: number;
  returnPct: number;
}

export const EquityCurveChart: React.FC<EquityCurveChartProps> = ({
  equityCurve,
  initialCapital,
  loading = false,
  height = 400,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const areaSeriesRef = useRef<ISeriesApi<'Area'> | null>(null);
  const baselineSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const [tooltipData, setTooltipData] = useState<TooltipData | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });

  // Transform data for lightweight-charts (requires Time type)
  const chartData: AreaData<Time>[] = equityCurve.map((point) => ({
    time: (new Date(point.date).getTime() / 1000) as Time, // Unix timestamp in seconds
    value: point.value,
  }));

  // Create lookup map for tooltip data
  const dataLookup = new Map(
    equityCurve.map((point) => [
      Math.floor(new Date(point.date).getTime() / 1000),
      {
        date: dayjs(point.date).format('MMM DD, YYYY'),
        equity: point.value,
        cash: point.cash,
        positions: point.positions_value,
        returnPct: ((point.value - initialCapital) / initialCapital) * 100,
      },
    ])
  );

  // Baseline data (initial capital reference line)
  const baselineData: LineData<Time>[] = equityCurve.length > 0
    ? [
        { time: chartData[0].time, value: initialCapital },
        { time: chartData[chartData.length - 1].time, value: initialCapital },
      ]
    : [];

  useEffect(() => {
    if (!chartContainerRef.current || equityCurve.length === 0) return;

    // Create chart
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#8c8c8c',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      rightPriceScale: {
        borderColor: '#d9d9d9',
      },
      timeScale: {
        borderColor: '#d9d9d9',
        timeVisible: true,
      },
      crosshair: {
        mode: 1, // Normal
      },
    });
    chartRef.current = chart;

    // Add area series for equity curve
    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor: '#1890ff',
      lineWidth: 2,
      topColor: 'rgba(24, 144, 255, 0.3)',
      bottomColor: 'rgba(24, 144, 255, 0)',
      priceFormat: {
        type: 'custom',
        formatter: (price: number) => {
          if (price >= 1000000) return `$${(price / 1000000).toFixed(1)}M`;
          if (price >= 1000) return `$${(price / 1000).toFixed(0)}K`;
          return `$${price.toFixed(0)}`;
        },
      },
    });
    areaSeriesRef.current = areaSeries;
    areaSeries.setData(chartData);

    // Add baseline (initial capital) reference line
    const baselineSeries = chart.addSeries(LineSeries, {
      color: '#8c8c8c',
      lineWidth: 1,
      lineStyle: 2, // Dashed
      priceLineVisible: false,
      lastValueVisible: false,
    });
    baselineSeriesRef.current = baselineSeries;
    baselineSeries.setData(baselineData);

    // Add crosshair move handler for tooltip
    chart.subscribeCrosshairMove((param) => {
      if (!param.point || !param.time) {
        setTooltipData(null);
        return;
      }

      const timestamp = typeof param.time === 'number' ? param.time : 0;
      const data = dataLookup.get(timestamp);
      if (data) {
        setTooltipData(data);
        setTooltipPosition({ x: param.point.x, y: param.point.y });
      }
    });

    // Fit content
    chart.timeScale().fitContent();

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [equityCurve, initialCapital, height]);

  if (loading) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <Spin size="large" />
        </div>
      </Card>
    );
  }

  if (!equityCurve || equityCurve.length === 0) {
    return (
      <Card>
        <Empty description="No equity curve data available" />
      </Card>
    );
  }

  return (
    <Card
      title={
        <span>
          <LineChartOutlined style={{ marginRight: 8 }} />
          Equity Curve
        </span>
      }
    >
      <div style={{ position: 'relative' }}>
        <div ref={chartContainerRef} style={{ width: '100%', height }} />
        
        {/* Custom tooltip */}
        {tooltipData && (
          <div
            style={{
              position: 'absolute',
              left: Math.min(tooltipPosition.x + 10, (chartContainerRef.current?.clientWidth ?? 300) - 200),
              top: Math.max(tooltipPosition.y - 80, 10),
              backgroundColor: 'rgba(255, 255, 255, 0.96)',
              border: '1px solid #d9d9d9',
              borderRadius: '4px',
              padding: '12px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
              pointerEvents: 'none',
              zIndex: 100,
            }}
          >
            <p style={{ margin: 0, fontWeight: 600, marginBottom: 8 }}>
              {tooltipData.date}
            </p>
            <p style={{ margin: 0, color: '#1890ff' }}>
              Total Equity: ${tooltipData.equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
            <p style={{ margin: 0, color: tooltipData.returnPct >= 0 ? '#52c41a' : '#ff4d4f' }}>
              Return: {tooltipData.returnPct >= 0 ? '+' : ''}{tooltipData.returnPct.toFixed(2)}%
            </p>
            <p style={{ margin: 0, color: '#8c8c8c', fontSize: '12px', marginTop: 4 }}>
              Cash: ${tooltipData.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
            <p style={{ margin: 0, color: '#8c8c8c', fontSize: '12px' }}>
              Positions: ${tooltipData.positions.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
        )}
        
        {/* Legend */}
        <div style={{ display: 'flex', justifyContent: 'center', paddingTop: '12px', gap: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: 20, height: 2, backgroundColor: '#1890ff' }} />
            <span style={{ fontSize: '12px', color: '#595959' }}>Portfolio Equity</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: 20, height: 2, backgroundColor: '#8c8c8c', borderStyle: 'dashed' }} />
            <span style={{ fontSize: '12px', color: '#595959' }}>Initial Capital</span>
          </div>
        </div>
      </div>
    </Card>
  );
};

export default EquityCurveChart;
