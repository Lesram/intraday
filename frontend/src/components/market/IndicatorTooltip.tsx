/**
 * Indicator Tooltip Component
 * 
 * Displays indicator values at the current crosshair position.
 * Shows a floating tooltip with values for all active indicators.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { Card } from 'antd';
import type { IChartApi, MouseEventParams, Time, ISeriesApi } from 'lightweight-charts';

interface IndicatorValue {
  name: string;
  displayName: string;
  color: string;
  value: number | null;
  additionalValues?: Array<{ label: string; value: number | null; color: string }>;
}

interface IndicatorTooltipProps {
  chart: IChartApi | null;
  indicators: Array<{
    id: string;
    config: {
      name: string;
      displayName: string;
      color: string;
    };
    series: ISeriesApi<'Line'> | ISeriesApi<'Histogram'> | null;
    additionalSeries?: Array<ISeriesApi<'Line'> | ISeriesApi<'Histogram'>>;
  }>;
  containerRef: React.RefObject<HTMLDivElement | null>;
}

/**
 * Format indicator value for display
 */
const formatValue = (value: number | null | undefined, indicator: string): string => {
  if (value === null || value === undefined || isNaN(value)) return '-';
  
  // Volume/OBV indicators - use abbreviated format
  if (['volume_ma', 'obv', 'ad'].includes(indicator)) {
    if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
    if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
    if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
    return value.toFixed(0);
  }
  
  // Price-based indicators
  if (['sma', 'ema', 'bollinger', 'vwap', 'atr'].includes(indicator)) {
    return value.toFixed(2);
  }
  
  // Percentage/oscillator indicators
  return value.toFixed(2);
};

/**
 * Get label for additional series values
 */
const getAdditionalLabel = (indicator: string, index: number): string => {
  if (indicator === 'bollinger') {
    return index === 0 ? 'Upper' : 'Lower';
  }
  if (indicator === 'macd') {
    return index === 0 ? 'Signal' : 'MACD';
  }
  if (indicator === 'donchian' || indicator === 'keltner') {
    return index === 0 ? 'Upper' : 'Lower';
  }
  return `Line ${index + 1}`;
};

export const IndicatorTooltip: React.FC<IndicatorTooltipProps> = ({
  chart,
  indicators,
  containerRef,
}) => {
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number } | null>(null);
  const [indicatorValues, setIndicatorValues] = useState<IndicatorValue[]>([]);
  const [isVisible, setIsVisible] = useState(false);

  const handleCrosshairMove = useCallback((param: MouseEventParams) => {
    if (!param || !param.point || param.point.x < 0 || param.point.y < 0) {
      setIsVisible(false);
      return;
    }

    // Calculate tooltip position
    const containerRect = containerRef.current?.getBoundingClientRect();
    if (!containerRect) return;

    // Position tooltip relative to crosshair
    const tooltipX = param.point.x + 15;
    const tooltipY = param.point.y - 10;

    setTooltipPosition({ x: tooltipX, y: tooltipY });

    // Get values for all indicators at this time point
    const values: IndicatorValue[] = [];

    for (const indicator of indicators) {
      if (!indicator.series) continue;

      try {
        // Get the data point at the crosshair position
        const time = param.time as Time | undefined;
        if (!time) continue;

        // Use seriesData with coordinates
        const seriesData = param.seriesData.get(indicator.series);
        const mainValue = seriesData ? (seriesData as { value?: number }).value ?? null : null;

        // Get additional series values (for multi-line indicators)
        const additionalValues: Array<{ label: string; value: number | null; color: string }> = [];
        
        if (indicator.additionalSeries) {
          indicator.additionalSeries.forEach((addSeries, index) => {
            const addData = param.seriesData.get(addSeries);
            const addValue = addData ? (addData as { value?: number }).value ?? null : null;
            additionalValues.push({
              label: getAdditionalLabel(indicator.config.name, index),
              value: addValue,
              color: indicator.config.color,
            });
          });
        }

        values.push({
          name: indicator.config.name,
          displayName: indicator.config.displayName,
          color: indicator.config.color,
          value: mainValue,
          additionalValues: additionalValues.length > 0 ? additionalValues : undefined,
        });
      } catch (err) {
        console.error(`Failed to get data for ${indicator.config.name}:`, err);
      }
    }

    setIndicatorValues(values);
    setIsVisible(values.length > 0 && values.some(v => v.value !== null));
  }, [indicators, containerRef]);

  useEffect(() => {
    if (!chart) return;

    chart.subscribeCrosshairMove(handleCrosshairMove);

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
    };
  }, [chart, handleCrosshairMove]);

  if (!isVisible || !tooltipPosition || indicatorValues.length === 0) {
    return null;
  }

  return (
    <Card
      size="small"
      style={{
        position: 'absolute',
        left: tooltipPosition.x,
        top: tooltipPosition.y,
        zIndex: 1000,
        background: 'rgba(26, 26, 26, 0.95)',
        border: '1px solid #333',
        borderRadius: 4,
        padding: 0,
        pointerEvents: 'none',
        minWidth: 120,
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.5)',
      }}
      styles={{ body: { padding: '8px 12px' } }}
    >
      {indicatorValues.map((ind, index) => (
        <div key={`${ind.name}-${index}`} style={{ marginBottom: ind.additionalValues ? 4 : 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div
              style={{
                width: 10,
                height: 3,
                background: ind.color,
                borderRadius: 1,
              }}
            />
            <span style={{ color: '#888', fontSize: 11 }}>
              {ind.displayName}:
            </span>
            <span style={{ color: '#fff', fontSize: 12, fontWeight: 500 }}>
              {formatValue(ind.value, ind.name)}
            </span>
          </div>
          
          {/* Additional values for multi-line indicators */}
          {ind.additionalValues && ind.additionalValues.map((addVal, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginLeft: 18,
                marginTop: 2,
              }}
            >
              <span style={{ color: '#666', fontSize: 10 }}>
                {addVal.label}:
              </span>
              <span style={{ color: '#ccc', fontSize: 11 }}>
                {formatValue(addVal.value, ind.name)}
              </span>
            </div>
          ))}
        </div>
      ))}
    </Card>
  );
};

export default IndicatorTooltip;
