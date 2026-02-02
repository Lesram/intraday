/**
 * Indicator Legend Component
 * 
 * Displays a compact legend of active indicators in the chart area.
 * Shows indicator name, color, and current value.
 */

import React from 'react';
import { Space, Tag } from 'antd';

interface IndicatorLegendProps {
  indicators: Array<{
    id: string;
    config: {
      name: string;
      displayName: string;
      color: string;
    };
  }>;
  style?: React.CSSProperties;
}

/**
 * Categorize indicator for display grouping
 */
const getIndicatorCategory = (name: string): 'overlay' | 'oscillator' | 'volume' => {
  const overlayIndicators = [
    'sma', 'ema', 'wma', 'vwma', 'tema', 'dema', 'trima', 'zlema',
    'bollinger', 'donchian', 'keltner', 'envelope',
    'ichimoku', 'parabolic_sar', 'supertrend', 'pivot',
    'vwap', 'twap', 'regression'
  ];
  
  const volumeIndicators = ['volume_ma', 'obv', 'ad', 'cmf'];
  
  if (overlayIndicators.includes(name)) return 'overlay';
  if (volumeIndicators.includes(name)) return 'volume';
  return 'oscillator';
};

export const IndicatorLegend: React.FC<IndicatorLegendProps> = ({
  indicators,
  style,
}) => {
  if (indicators.length === 0) return null;

  // Group indicators by category
  const overlays = indicators.filter(i => getIndicatorCategory(i.config.name) === 'overlay');
  const oscillators = indicators.filter(i => getIndicatorCategory(i.config.name) === 'oscillator');
  const volumes = indicators.filter(i => getIndicatorCategory(i.config.name) === 'volume');

  const renderIndicatorTags = (items: typeof indicators, label: string) => {
    if (items.length === 0) return null;
    
    return (
      <div style={{ marginBottom: 4 }}>
        <span style={{ color: '#666', fontSize: 10, marginRight: 4 }}>{label}:</span>
        <Space size={4} wrap>
          {items.map((ind) => (
            <Tag
              key={ind.id}
              style={{
                background: 'rgba(0, 0, 0, 0.6)',
                borderColor: ind.config.color,
                borderWidth: 1,
                color: ind.config.color,
                fontSize: 10,
                padding: '0 6px',
                margin: 0,
              }}
            >
              <span
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 2,
                  background: ind.config.color,
                  marginRight: 4,
                  verticalAlign: 'middle',
                }}
              />
              {ind.config.displayName}
            </Tag>
          ))}
        </Space>
      </div>
    );
  };

  return (
    <div
      style={{
        position: 'absolute',
        top: 8,
        left: 8,
        zIndex: 100,
        background: 'rgba(20, 20, 20, 0.85)',
        borderRadius: 4,
        padding: '6px 10px',
        maxWidth: 300,
        ...style,
      }}
    >
      {renderIndicatorTags(overlays, 'Overlays')}
      {renderIndicatorTags(oscillators, 'Oscillators')}
      {renderIndicatorTags(volumes, 'Volume')}
    </div>
  );
};

export default IndicatorLegend;
