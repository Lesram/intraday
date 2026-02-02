/**
 * Chart Hook
 * React hook for managing Lightweight Charts instance
 */

import { useRef, useEffect, useState, useCallback } from 'react';
import { 
  createChart, 
  ColorType,
  CrosshairMode,
  LineStyle,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type Time,
  type IChartApi,
  type MouseEventParams
} from 'lightweight-charts';
import type { 
  ChartOptions, 
  ChartSeries, 
  CandlestickData, 
  VolumeData,
  Bar 
} from '../types/chart.types';

/**
 * Default chart theme (dark mode)
 */
const DEFAULT_THEME = {
  background: '#1a1a1a',
  textColor: '#d1d5db',
  gridColor: '#2d2d2d',
  upColor: '#22c55e',
  downColor: '#ef4444',
  borderUpColor: '#22c55e',
  borderDownColor: '#ef4444',
  wickUpColor: '#22c55e',
  wickDownColor: '#ef4444',
  volumeUpColor: 'rgba(34, 197, 94, 0.5)',
  volumeDownColor: 'rgba(239, 68, 68, 0.5)',
};

/**
 * Hook for managing chart instance
 */
export function useChart(containerRef: React.RefObject<HTMLDivElement | null>, options?: ChartOptions) {
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ChartSeries>({
    indicators: new Map(),
  });
  const [isReady, setIsReady] = useState(false);

  /**
   * Initialize chart
   */
  useEffect(() => {
    if (!containerRef.current) {
      // Container not ready yet - this is normal during initial render
      return;
    }

    // Check if container has dimensions
    const container = containerRef.current;
    if (container.clientWidth === 0 || container.clientHeight === 0) {
      // Container has no dimensions yet, waiting for layout
      return;
    }
    
    // Don't initialize if chart already exists and is valid
    if (chartRef.current) {
      console.log('Chart already initialized, skipping');
      return;
    }

    console.log('Initializing chart with container dimensions:', container.clientWidth, container.clientHeight);

    const theme = options?.theme || DEFAULT_THEME;

    try {
      // Create chart with autoSize (don't specify width/height when autoSize is true)
      const chart = createChart(container, {
        autoSize: true,  // Enable auto-resize - will use container dimensions
        layout: {
          background: { type: ColorType.Solid, color: theme.background },
          textColor: theme.textColor,
        },
      grid: {
        vertLines: { 
          color: theme.gridColor,
          visible: options?.showGrid !== false,
        },
        horzLines: { 
          color: theme.gridColor,
          visible: options?.showGrid !== false,
        },
      },
      crosshair: {
        mode: options?.showCrosshair !== false ? CrosshairMode.Normal : CrosshairMode.Hidden,
        vertLine: {
          width: 1,
          color: theme.gridColor,
          style: LineStyle.Dashed,
        },
        horzLine: {
          width: 1,
          color: theme.gridColor,
          style: LineStyle.Dashed,
        },
      },
      rightPriceScale: {
        visible: options?.showPriceScale !== false,
        borderColor: theme.gridColor,
      },
      timeScale: {
        visible: options?.showTimeScale !== false,
        borderColor: theme.gridColor,
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    });

    // Create candlestick series - v5 API uses SeriesDefinition constants
    // Reserve bottom 35% for oscillator indicators
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: theme.upColor,
      downColor: theme.downColor,
      borderUpColor: theme.borderUpColor,
      borderDownColor: theme.borderDownColor,
      wickUpColor: theme.wickUpColor,
      wickDownColor: theme.wickDownColor,
      priceScaleId: 'right',
    });
    
    // Configure price scale to use top 65% of chart, leaving bottom for indicators
    chart.priceScale('right').applyOptions({
      scaleMargins: {
        top: 0.02,
        bottom: 0.35, // Leave 35% for oscillators
      },
    });

    // Create volume series - v5 API uses SeriesDefinition constants
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: theme.volumeUpColor,
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'volume',
    });

    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });

    chartRef.current = chart;
    seriesRef.current.candlestick = candlestickSeries;
    seriesRef.current.volume = volumeSeries;
    setIsReady(true);

    console.log('Chart initialized successfully');

    // Resize handled automatically by autoSize: true, no need for manual resize handler

    // Cleanup
    return () => {
      console.log('Cleaning up chart');
      
      // Clear series refs BEFORE removing chart
      seriesRef.current.candlestick = undefined;
      seriesRef.current.volume = undefined;
      
      if (chartRef.current) {
        try {
          chartRef.current.remove();
        } catch (err) {
          console.error('Error removing chart:', err);
        }
        chartRef.current = null;
      }
      setIsReady(false);
    };
    } catch (error) {
      console.error('Failed to initialize chart:', error);
      setIsReady(false);
      return;
    }
  }, [options]); // Only options, not containerRef (refs are stable)

  /**
  /**
   * Set candlestick data
   */
  const setCandlestickData = useCallback((data: CandlestickData[]) => {
    if (seriesRef.current.candlestick) {
      seriesRef.current.candlestick.setData(data);
    }
  }, []);

  /**
   * Update candlestick (add or update last bar)
   */
  const updateCandlestick = useCallback((data: CandlestickData) => {
    if (seriesRef.current.candlestick) {
      seriesRef.current.candlestick.update(data);
    }
  }, []);

  /**
   * Set volume data
   */
  const setVolumeData = useCallback((data: VolumeData[]) => {
    if (seriesRef.current.volume) {
      seriesRef.current.volume.setData(data);
    }
  }, []);

  /**
   * Update volume (add or update last bar)
   */
  const updateVolume = useCallback((data: VolumeData) => {
    if (seriesRef.current.volume) {
      seriesRef.current.volume.update(data);
    }
  }, []);

  /**
   * Set bars data (converts Bar[] to candlestick and volume)
   */
  const setBarsData = useCallback((bars: Bar[]) => {
    const theme = options?.theme || DEFAULT_THEME;
    
    const candlestickData: CandlestickData[] = bars.map(bar => ({
      time: bar.time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    }));

    const volumeData: VolumeData[] = bars.map(bar => ({
      time: bar.time,
      value: bar.volume,
      color: bar.close >= bar.open ? theme.volumeUpColor : theme.volumeDownColor,
    }));

    setCandlestickData(candlestickData);
    setVolumeData(volumeData);
  }, [setCandlestickData, setVolumeData, options?.theme]);

  /**
   * Update with new bar (real-time)
   */
  const updateBar = useCallback((bar: Bar) => {
    const theme = options?.theme || DEFAULT_THEME;
    
    updateCandlestick({
      time: bar.time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    });

    updateVolume({
      time: bar.time,
      value: bar.volume,
      color: bar.close >= bar.open ? theme.volumeUpColor : theme.volumeDownColor,
    });
  }, [updateCandlestick, updateVolume, options?.theme]);

  /**
   * Add indicator line series
   */
  const addIndicator = useCallback((id: string, color: string, name: string) => {
    if (!chartRef.current) return;

    const series = chartRef.current.addSeries(LineSeries, {
      color,
      lineWidth: 2,
      title: name,
    });

    seriesRef.current.indicators.set(id, series);
    return series;
  }, []);

  /**
   * Remove indicator
   */
  const removeIndicator = useCallback((id: string) => {
    const series = seriesRef.current.indicators.get(id);
    if (series && chartRef.current) {
      // Cast to unknown first then to the expected type for removeSeries
      chartRef.current.removeSeries(series as unknown as Parameters<IChartApi['removeSeries']>[0]);
      seriesRef.current.indicators.delete(id);
    }
  }, []);

  /**
   * Update indicator data
   */
  const updateIndicator = useCallback((id: string, data: Array<{ time: Time; value: number }>) => {
    const series = seriesRef.current.indicators.get(id);
    if (series) {
      series.setData(data);
    }
  }, []);

  /**
   * Fit content
   */
  const fitContent = useCallback(() => {
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, []);

  /**
   * Subscribe to crosshair move
   */
  const subscribeCrosshairMove = useCallback((
    handler: (param: MouseEventParams) => void
  ) => {
    if (chartRef.current) {
      chartRef.current.subscribeCrosshairMove(handler);
    }
  }, []);

  /**
   * Unsubscribe from crosshair move
   */
  const unsubscribeCrosshairMove = useCallback((
    handler: (param: MouseEventParams) => void
  ) => {
    if (chartRef.current) {
      chartRef.current.unsubscribeCrosshairMove(handler);
    }
  }, []);

  return {
    chart: chartRef.current,
    series: seriesRef.current,
    isReady,
    
    // Data methods
    setCandlestickData,
    updateCandlestick,
    setVolumeData,
    updateVolume,
    setBarsData,
    updateBar,
    
    // Indicator methods
    addIndicator,
    removeIndicator,
    updateIndicator,
    
    // Utility methods
    fitContent,
    subscribeCrosshairMove,
    unsubscribeCrosshairMove,
  };
}
