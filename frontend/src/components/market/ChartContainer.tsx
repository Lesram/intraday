/**
 * Chart Container Component
 * Main chart component using Lightweight Charts
 */

import React, { useRef, useEffect, useState, useMemo } from 'react';
import { Card, Space, Select, Button, Spin, DatePicker } from 'antd';
import { FullscreenOutlined, SettingOutlined } from '@ant-design/icons';
import { useChart } from '../../hooks/useChart';
import type { Timeframe, Bar } from '../../types/chart.types';
import type { IChartApi } from 'lightweight-charts';
import dayjs, { Dayjs } from 'dayjs';

const { Option } = Select;
const { RangePicker } = DatePicker;

interface ChartContainerProps {
  symbol: string;
  onSymbolChange?: (symbol: string) => void;
  onChartReady?: (chart: IChartApi | null) => void;
}

/**
 * Timeframe display labels
 */
const TIMEFRAME_LABELS: Record<Timeframe, string> = {
  '1m': '1 Min',
  '5m': '5 Min',
  '15m': '15 Min',
  '30m': '30 Min',
  '1h': '1 Hour',
  '4h': '4 Hours',
  '1D': '1 Day',
  '1W': '1 Week',
  '1M': '1 Month',
};

/**
 * Chart Container Component
 */
export const ChartContainer: React.FC<ChartContainerProps> = ({ 
  symbol,
  onChartReady
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [timeframe, setTimeframe] = useState<Timeframe>('5m');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Date range state
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(1, 'month'), // Default: 1 month ago
    dayjs() // Today
  ]);
  const [selectedRangePreset, setSelectedRangePreset] = useState<string>('1M');

  const {
    chart,
    isReady,
    setBarsData,
    fitContent,
  } = useChart(containerRef);

  // Create stable date range key for dependency tracking
  const dateRangeKey = useMemo(
    () => `${dateRange[0].format('YYYY-MM-DD')}_${dateRange[1].format('YYYY-MM-DD')}`,
    [dateRange]
  );

  // Range presets
  const rangePresets = [
    { label: '1D', value: '1D', days: 1 },
    { label: '5D', value: '5D', days: 5 },
    { label: '1M', value: '1M', days: 30 },
    { label: '3M', value: '3M', days: 90 },
    { label: '6M', value: '6M', days: 180 },
    { label: '1Y', value: '1Y', days: 365 },
    { label: 'YTD', value: 'YTD', days: dayjs().diff(dayjs().startOf('year'), 'day') },
  ];

  // Notify parent when chart is ready
  useEffect(() => {
    if (chart && onChartReady) {
      onChartReady(chart);
    }
  }, [chart, onChartReady]);

  /**
   * Fetch historical data
   */
  useEffect(() => {
    if (!isReady || !symbol) return;

    // Request deduplication - prevent rapid successive identical calls
    const requestKey = `${symbol}_${timeframe}_${dateRangeKey}`;
    let isCancelled = false;

    const fetchData = async () => {
      // Prevent concurrent requests with same parameters
      if (isCancelled) {
        console.log('[ChartContainer] Request cancelled:', requestKey);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        // Fetch real data from API with date range
        const { fetchHistoricalBars } = await import('../../services/marketDataApi');
        
        // Convert date range to API format
        const startDate = dateRange[0].format('YYYY-MM-DD');
        const endDate = dateRange[1].format('YYYY-MM-DD');
        
        // Calculate appropriate limit based on timeframe
        // API supports up to 10,000 bars - use maximum for best coverage
        const limitByTimeframe: Record<string, number> = {
          '1m': 10000,   // ~25 trading days
          '5m': 10000,   // ~128 trading days (~6 months)
          '15m': 10000,  // ~385 trading days (~1.5 years)
          '30m': 10000,  // ~769 trading days (~3 years)
          '1h': 10000,   // ~1428 trading days (~5.5 years)
          '4h': 10000,   // ~1428 trading days (~5.5 years)
          '1D': 10000,   // 10000 trading days (~40 years)
          '1W': 10000,   // 10000 weeks (~192 years)
          '1M': 10000,   // 10000 months (~833 years)
        };
        const limit = limitByTimeframe[timeframe] || 10000;
        
        console.log(`[ChartContainer] Fetching bars for ${symbol}:`, {
          timeframe,
          startDate,
          endDate,
          limit,
          requestKey
        });
        
        const bars = await fetchHistoricalBars(symbol, timeframe, { 
          limit,
          start: startDate,
          end: endDate
        });
        
        // Check if request was cancelled while fetching
        if (isCancelled) {
          console.log('[ChartContainer] Request cancelled after fetch:', requestKey);
          return;
        }
        
        console.log(`[ChartContainer] Received ${bars?.length || 0} bars`);
        
        if (bars && bars.length > 0) {
          console.log(`[ChartContainer] Setting ${bars.length} bars on chart`);
          setBarsData(bars);
          fitContent();
        } else {
          // NO MOCK DATA - Show error state instead of fake data
          console.warn('[ChartContainer] API returned empty bars, no data available');
          setError('No chart data available for this symbol and timeframe. Try a different date range or timeframe.');
        }
      } catch (err: unknown) {
        // Don't process errors if request was cancelled
        if (isCancelled) return;
        
        // Handle auth errors - user must be logged in for real data
        const axiosError = err as { response?: { status?: number; data?: { detail?: string } } };
        if (axiosError?.response?.status === 401) {
          setError('Please log in to view real-time chart data.');
        } else {
          console.error('Failed to fetch chart data:', err);
          setError(`Failed to load chart data: ${axiosError?.response?.data?.detail || 'Unknown error'}`);
        }
        // NO MOCK DATA - Do not fallback to fake data
      } finally {
        if (!isCancelled) {
          setLoading(false);
        }
      }
    };

    fetchData();

    // Cleanup function to cancel request if component unmounts or dependencies change
    return () => {
      isCancelled = true;
    };
  }, [symbol, timeframe, dateRangeKey, isReady]);

  /**
   * Handle timeframe change
   */
  const handleTimeframeChange = (newTimeframe: Timeframe) => {
    setTimeframe(newTimeframe);
  };

  /**
   * Handle range preset click
   */
  const handleRangePreset = (preset: typeof rangePresets[0]) => {
    setSelectedRangePreset(preset.value);
    if (preset.value === 'YTD') {
      setDateRange([dayjs().startOf('year'), dayjs()]);
    } else {
      setDateRange([dayjs().subtract(preset.days, 'day'), dayjs()]);
    }
  };

  /**
   * Handle custom date range change
   */
  const handleDateRangeChange = (dates: null | [Dayjs | null, Dayjs | null]) => {
    if (dates && dates[0] && dates[1]) {
      setDateRange([dates[0], dates[1]]);
      setSelectedRangePreset(''); // Clear preset selection
    }
  };

  /**
   * Handle fullscreen
   */
  const handleFullscreen = () => {
    if (containerRef.current) {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else {
        containerRef.current.requestFullscreen();
      }
    }
  };

  return (
    <Card
      title={
        <Space wrap>
          <span style={{ fontSize: 16, fontWeight: 600 }}>{symbol}</span>
          <Select
            value={timeframe}
            onChange={handleTimeframeChange}
            style={{ width: 120 }}
            size="small"
          >
            {Object.entries(TIMEFRAME_LABELS).map(([value, label]) => (
              <Option key={value} value={value}>
                {label}
              </Option>
            ))}
          </Select>
          
          {/* Range Preset Buttons */}
          <Space size="small">
            {rangePresets.map((preset) => (
              <Button
                key={preset.value}
                size="small"
                type={selectedRangePreset === preset.value ? 'primary' : 'default'}
                onClick={() => handleRangePreset(preset)}
              >
                {preset.label}
              </Button>
            ))}
          </Space>
          
          {/* Custom Date Range Picker */}
          <RangePicker
            size="small"
            value={dateRange}
            onChange={handleDateRangeChange}
            format="MMM DD, YYYY"
            allowClear={false}
          />
        </Space>
      }
      extra={
        <Space>
          <Button 
            icon={<SettingOutlined />} 
            size="small"
            type="text"
          />
          <Button 
            icon={<FullscreenOutlined />} 
            size="small"
            type="text"
            onClick={handleFullscreen}
          />
        </Space>
      }
      style={{ height: '100%' }}
      styles={{ body: { padding: 0, height: 'calc(100% - 57px)' } }}
    >
      {loading && (
        <div style={{ 
          position: 'absolute', 
          top: '50%', 
          left: '50%', 
          transform: 'translate(-50%, -50%)',
          zIndex: 10
        }}>
          <Spin size="large" />
        </div>
      )}
      
      {error && (
        <div style={{ 
          position: 'absolute', 
          top: '50%', 
          left: '50%', 
          transform: 'translate(-50%, -50%)',
          color: '#ff4d4f',
          zIndex: 10
        }}>
          {error}
        </div>
      )}

      <div 
        ref={containerRef} 
        style={{ 
          width: '100%', 
          height: '100%',
          minHeight: '500px',
          position: 'relative'
        }} 
      />
    </Card>
  );
};

export default ChartContainer;
