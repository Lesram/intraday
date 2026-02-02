/**
 * useIndicators Hook
 * 
 * Manages technical indicators: fetching data, adding to chart, caching results.
 * 
 * Features:
 * - Fetch indicator data from backend API
 * - Add/remove indicators to/from chart
 * - Update indicator parameters
 * - Cache indicator results
 * - Handle loading/error states
 * 
 * Phase 7 - Market Data & Charting
 * Created: October 16, 2025
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { App } from 'antd';
import { LineSeries, HistogramSeries, type IChartApi, type ISeriesApi, type Time, type LineData, type HistogramData } from 'lightweight-charts';
import type { IndicatorConfig } from '../components/market/IndicatorPanel';
import { apiClient } from '../services/api';

// ============================================================================
// TYPES
// ============================================================================

interface IndicatorData {
  symbol: string;
  indicator: string;
  timeframe: string;
  values: Record<string, unknown>;
  params: Record<string, number>;
}

interface IndicatorSeries {
  id: string;
  config: IndicatorConfig;
  series: ISeriesApi<'Line'> | ISeriesApi<'Histogram'> | null;
  // Additional series for multi-line indicators (e.g., Bollinger upper/lower bands)
  additionalSeries?: Array<ISeriesApi<'Line'> | ISeriesApi<'Histogram'>>;
  data: IndicatorData | null;
}

interface UseIndicatorsProps {
  chart: IChartApi | null;
  symbol: string;
  timeframe: string;
}

interface UseIndicatorsReturn {
  indicators: IndicatorSeries[];
  loading: boolean;
  error: string | null;
  addIndicator: (config: IndicatorConfig) => Promise<void>;
  removeIndicator: (id: string) => void;
  updateIndicator: (id: string, updates: Partial<IndicatorConfig>) => Promise<void>;
  clearIndicators: () => void;
  refreshIndicators: () => Promise<void>;
}

// ============================================================================
// API CLIENT
// ============================================================================

class IndicatorsAPI {
  async calculateIndicator(
    symbol: string,
    indicator: string,
    timeframe: string,
    params: Record<string, number>,
    start: Date,
    end: Date
  ): Promise<IndicatorData> {
    try {
      const response = await apiClient.post('/indicators/calculate', {
        symbol,
        indicator,
        timeframe,
        start: start.toISOString(),
        end: end.toISOString(),
        params,
      });
      
      return response.data;
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: unknown }; message?: string };
      console.error(`Failed to calculate ${indicator}:`, axiosError.response?.data || axiosError.message);
      throw error;
    }
  }

  async calculateBatch(
    symbol: string,
    timeframe: string,
    indicators: Array<{ indicator: string; params: Record<string, number> }>,
    start: Date,
    end: Date
  ): Promise<{ symbol: string; results: IndicatorData[] }> {
    const response = await apiClient.post('/indicators/batch', {
      symbol,
      timeframe,
      start: start.toISOString(),
      end: end.toISOString(),
      indicators,
    });

    return response.data;
  }
}

// ============================================================================
// HOOK
// ============================================================================

export const useIndicators = ({
  chart,
  symbol,
  timeframe,
}: UseIndicatorsProps): UseIndicatorsReturn => {
  // Get message API from App context
  const { message } = App.useApp();
  
  // State
  const [indicators, setIndicators] = useState<IndicatorSeries[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Refs
  const apiRef = useRef(new IndicatorsAPI());
  const cacheRef = useRef<Map<string, IndicatorData>>(new Map());

  // Generate cache key
  const getCacheKey = useCallback(
    (indicator: string, params: Record<string, number>) => {
      const paramsStr = Object.entries(params)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => `${k}=${v}`)
        .join('&');
      return `${symbol}_${indicator}_${timeframe}_${paramsStr}`;
    },
    [symbol, timeframe]
  );

  // Get dedicated scale ID for indicator
  const getScaleIdForIndicator = useCallback((indicatorName: string): string => {
    // OVERLAY INDICATORS: Display on main price scale (right)
    // These are price-based indicators that make sense at stock price levels
    const overlayIndicators = [
      'sma', 'ema', 'wma', 'vwma', 'tema', 'dema', 'trima', 'zlema',
      'bollinger', 'donchian', 'keltner', 'envelope',
      'ichimoku', 'parabolic_sar', 'supertrend', 'pivot',
      'vwap', 'twap', 'regression'
    ];
    
    // BOUNDED OSCILLATORS (0-100 range): Get dedicated scale
    const boundedOscillators: Record<string, string> = {
      'rsi': 'rsi-scale',           // 0-100
      'stochastic': 'stoch-scale',  // 0-100  
      'williams_r': 'williams-scale', // -100 to 0
      'mfi': 'mfi-scale',           // 0-100
    };
    
    // MOMENTUM INDICATORS: Get dedicated scales (unbounded, can go negative)
    const momentumIndicators: Record<string, string> = {
      'macd': 'macd-scale',
      'cci': 'cci-scale',
      'roc': 'roc-scale',
      'tsi': 'tsi-scale',
      'adx': 'adx-scale',
      'aroon': 'aroon-scale',
      'ultimate': 'ultimate-scale',
      'awesome': 'awesome-scale',
    };
    
    // VOLATILITY INDICATORS: Get dedicated scales
    const volatilityIndicators: Record<string, string> = {
      'atr': 'atr-scale',
    };
    
    // VOLUME INDICATORS: Get dedicated scale
    const volumeIndicators: Record<string, string> = {
      'volume_ma': 'volume-scale',
      'obv': 'obv-scale',
      'ad': 'ad-scale',
      'cmf': 'cmf-scale',
    };
    
    // Determine scale ID
    if (overlayIndicators.includes(indicatorName)) {
      return 'right'; // Share main price scale
    } else if (boundedOscillators[indicatorName]) {
      return boundedOscillators[indicatorName];
    } else if (momentumIndicators[indicatorName]) {
      return momentumIndicators[indicatorName];
    } else if (volatilityIndicators[indicatorName]) {
      return volatilityIndicators[indicatorName];
    } else if (volumeIndicators[indicatorName]) {
      return volumeIndicators[indicatorName];
    }
    
    // Default: separate scale
    return `${indicatorName}-scale`;
  }, []);

  // Configure scale options for indicator
  // Uses fixed positions so oscillators appear below price chart
  // Price chart uses top 65% (bottom margin 0.35), oscillators use bottom 35%
  const configureScale = useCallback((indicatorName: string, scaleId: string, paneIndex: number = 0) => {
    if (!chart || scaleId === 'right') return; // Don't configure main price scale
    
    const scale = chart.priceScale(scaleId);
    
    // Oscillator indicators drawn in bottom 35% of chart
    // scaleMargins: top = % empty above, bottom = % empty below
    // For oscillators: top should be 0.65+ (below price), bottom varies by indicator
    // Stack oscillators in distinct zones to avoid overlap
    const oscillatorZones: Record<string, { top: number; bottom: number; showScale: boolean }> = {
      // RSI zone: 65-82% from top (first oscillator zone)
      'rsi': { top: 0.65, bottom: 0.18, showScale: true },
      'mfi': { top: 0.65, bottom: 0.18, showScale: true },
      'williams_r': { top: 0.65, bottom: 0.18, showScale: true },
      'stochastic': { top: 0.65, bottom: 0.18, showScale: true },
      
      // MACD zone: 72-90% from top (second oscillator zone)
      'macd': { top: 0.72, bottom: 0.10, showScale: true },
      'cci': { top: 0.72, bottom: 0.10, showScale: true },
      
      // ATR/ADX zone: 80-95% from top (third zone)
      'atr': { top: 0.80, bottom: 0.05, showScale: true },
      'adx': { top: 0.80, bottom: 0.05, showScale: true },
      'roc': { top: 0.80, bottom: 0.05, showScale: true },
      
      // Volume zone: very bottom (85-100% from top)
      'volume_ma': { top: 0.85, bottom: 0, showScale: false },
      'obv': { top: 0.85, bottom: 0, showScale: false },
      'ad': { top: 0.85, bottom: 0, showScale: false },
      'cmf': { top: 0.85, bottom: 0, showScale: false },
      
      // Other momentum - share with MACD zone
      'tsi': { top: 0.72, bottom: 0.10, showScale: true },
      'aroon': { top: 0.72, bottom: 0.10, showScale: true },
      'ultimate': { top: 0.72, bottom: 0.10, showScale: true },
      'awesome': { top: 0.72, bottom: 0.10, showScale: true },
    };
    
    const zone = oscillatorZones[indicatorName] || { top: 0.70, bottom: 0.10, showScale: true };
    
    scale.applyOptions({
      scaleMargins: {
        top: zone.top,
        bottom: zone.bottom,
      },
      autoScale: true,
      visible: zone.showScale, // Show scale for oscillators to see values
      borderColor: '#333',
    });
    
    console.log(`[useIndicators] Configured scale for ${indicatorName}: top=${zone.top}, bottom=${zone.bottom}, visible=${zone.showScale}`);
  }, [chart]);

  // Create series on chart
  // Returns main series and optionally additional series for multi-line indicators
  const createSeries = useCallback(
    (config: IndicatorConfig): { 
      main: ISeriesApi<'Line'> | ISeriesApi<'Histogram'> | null;
      additional?: Array<ISeriesApi<'Line'> | ISeriesApi<'Histogram'>>;
    } => {
      if (!chart) {
        console.error('Cannot create series: chart is null');
        return { main: null };
      }

      try {
        const scaleId = getScaleIdForIndicator(config.name);
        const isHistogram = ['volume_ma', 'obv', 'ad', 'macd'].includes(config.name);
        
        console.log(`[useIndicators] Creating series for ${config.name}:`, {
          scaleId,
          isHistogram,
          color: config.color,
        });

        // Create main series with dedicated scale
        let series;
        if (isHistogram) {
          series = chart.addSeries(HistogramSeries, {
            color: config.color,
            priceFormat: {
              type: 'volume',
            },
            priceScaleId: scaleId,
          });
        } else {
          series = chart.addSeries(LineSeries, {
            color: config.color,
            lineWidth: 2,
            priceScaleId: scaleId,
          });
        }
        
        // Configure the scale
        configureScale(config.name, scaleId);
        
        // For Bollinger Bands, create additional series for upper and lower bands
        const additionalSeries: Array<ISeriesApi<'Line'> | ISeriesApi<'Histogram'>> = [];
        
        if (config.name === 'bollinger') {
          // Upper band - lighter color
          const upperSeries = chart.addSeries(LineSeries, {
            color: config.color,
            lineWidth: 1,
            lineStyle: 2, // Dashed
            priceScaleId: scaleId,
          });
          additionalSeries.push(upperSeries);
          
          // Lower band - lighter color
          const lowerSeries = chart.addSeries(LineSeries, {
            color: config.color,
            lineWidth: 1,
            lineStyle: 2, // Dashed
            priceScaleId: scaleId,
          });
          additionalSeries.push(lowerSeries);
          
          console.log(`[useIndicators] Created additional Bollinger band series`);
        }
        
        // For Donchian/Keltner channels, create additional series
        if (config.name === 'donchian' || config.name === 'keltner') {
          // Upper band
          const upperSeries = chart.addSeries(LineSeries, {
            color: config.color,
            lineWidth: 1,
            lineStyle: 2,
            priceScaleId: scaleId,
          });
          additionalSeries.push(upperSeries);
          
          // Lower band
          const lowerSeries = chart.addSeries(LineSeries, {
            color: config.color,
            lineWidth: 1,
            lineStyle: 2,
            priceScaleId: scaleId,
          });
          additionalSeries.push(lowerSeries);
        }
        
        // For Pivot Points, create support and resistance lines
        if (config.name === 'pivot_points' || config.name === 'pivot') {
          // S1 - Support 1 (green)
          additionalSeries.push(chart.addSeries(LineSeries, {
            color: '#22c55e',
            lineWidth: 1,
            lineStyle: 2,
            priceScaleId: scaleId,
          }));
          // S2 - Support 2 (green, lighter)
          additionalSeries.push(chart.addSeries(LineSeries, {
            color: 'rgba(34, 197, 94, 0.6)',
            lineWidth: 1,
            lineStyle: 2,
            priceScaleId: scaleId,
          }));
          // R1 - Resistance 1 (red)
          additionalSeries.push(chart.addSeries(LineSeries, {
            color: '#ef4444',
            lineWidth: 1,
            lineStyle: 2,
            priceScaleId: scaleId,
          }));
          // R2 - Resistance 2 (red, lighter)
          additionalSeries.push(chart.addSeries(LineSeries, {
            color: 'rgba(239, 68, 68, 0.6)',
            lineWidth: 1,
            lineStyle: 2,
            priceScaleId: scaleId,
          }));
        }
        
        // For MACD, also create signal line
        if (config.name === 'macd') {
          const signalSeries = chart.addSeries(LineSeries, {
            color: '#ff6b6b', // Red for signal line
            lineWidth: 1,
            priceScaleId: scaleId,
          });
          additionalSeries.push(signalSeries);
          
          const macdLineSeries = chart.addSeries(LineSeries, {
            color: '#4dabf7', // Blue for MACD line
            lineWidth: 1,
            priceScaleId: scaleId,
          });
          additionalSeries.push(macdLineSeries);
          
          // Add MACD zero reference line
          macdLineSeries.createPriceLine({
            price: 0,
            color: 'rgba(255, 255, 255, 0.3)',
            lineWidth: 1,
            lineStyle: 2, // Dashed
            axisLabelVisible: false,
            title: '',
          });
        }
        
        // Add reference lines for RSI (30 oversold, 70 overbought)
        if (config.name === 'rsi') {
          // Oversold line at 30
          series.createPriceLine({
            price: 30,
            color: 'rgba(34, 197, 94, 0.5)', // Green (oversold = potential buy)
            lineWidth: 1,
            lineStyle: 2, // Dashed
            axisLabelVisible: false,
            title: '',
          });
          // Overbought line at 70
          series.createPriceLine({
            price: 70,
            color: 'rgba(239, 68, 68, 0.5)', // Red (overbought = potential sell)
            lineWidth: 1,
            lineStyle: 2, // Dashed
            axisLabelVisible: false,
            title: '',
          });
          // Neutral line at 50
          series.createPriceLine({
            price: 50,
            color: 'rgba(255, 255, 255, 0.2)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: false,
            title: '',
          });
        }
        
        // Add reference lines for Stochastic
        if (config.name === 'stochastic') {
          series.createPriceLine({
            price: 20,
            color: 'rgba(34, 197, 94, 0.5)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: false,
            title: '',
          });
          series.createPriceLine({
            price: 80,
            color: 'rgba(239, 68, 68, 0.5)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: false,
            title: '',
          });
        }
        
        // Add reference lines for Williams %R (-20 overbought, -80 oversold)
        if (config.name === 'williams_r') {
          series.createPriceLine({
            price: -20,
            color: 'rgba(239, 68, 68, 0.5)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: false,
            title: '',
          });
          series.createPriceLine({
            price: -80,
            color: 'rgba(34, 197, 94, 0.5)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: false,
            title: '',
          });
        }
        
        // Add reference lines for CCI (+100/-100 standard levels)
        if (config.name === 'cci') {
          series.createPriceLine({
            price: 100,
            color: 'rgba(239, 68, 68, 0.5)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: false,
            title: '',
          });
          series.createPriceLine({
            price: -100,
            color: 'rgba(34, 197, 94, 0.5)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: false,
            title: '',
          });
          series.createPriceLine({
            price: 0,
            color: 'rgba(255, 255, 255, 0.2)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: false,
            title: '',
          });
        }
        
        // Add reference lines for MFI
        if (config.name === 'mfi') {
          series.createPriceLine({
            price: 20,
            color: 'rgba(34, 197, 94, 0.5)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: false,
            title: '',
          });
          series.createPriceLine({
            price: 80,
            color: 'rgba(239, 68, 68, 0.5)',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: false,
            title: '',
          });
        }
        
        console.log(`[useIndicators] Created series for ${config.name} on scale '${scaleId}'`);
        return { main: series, additional: additionalSeries.length > 0 ? additionalSeries : undefined };
      } catch (err) {
        console.error('Failed to create series:', err);
        return { main: null };
      }
    },
    [chart, getScaleIdForIndicator, configureScale]
  );

  // Convert indicator data to chart format
  // For multi-line indicators, returns { main: data, additional: [data1, data2, ...] }
  const convertToChartData = useCallback(
    (indicatorData: IndicatorData, indicator: string): { 
      main: LineData[] | HistogramData[];
      additional?: Array<LineData[] | HistogramData[]>;
    } => {
      console.log(`[convertToChartData] Converting ${indicator}:`, {
        indicatorData,
        hasValues: !!indicatorData?.values,
        valuesType: typeof indicatorData?.values,
        valuesKeys: indicatorData?.values ? Object.keys(indicatorData.values).slice(0, 10) : [],
      });

      const { values } = indicatorData;
      
      if (!values) {
        console.warn(`[convertToChartData] No values in indicatorData for ${indicator}`);
        return { main: [] };
      }
      
      // Helper to filter out null/undefined values
      const filterValidEntries = (entries: [string, unknown][]): [string, number][] => {
        const filtered = entries.filter(([_key, value]) => value !== null && value !== undefined && !isNaN(value as number)) as [string, number][];
        console.log(`[convertToChartData] Filtered ${entries.length} entries to ${filtered.length} valid entries`);
        return filtered;
      };
      
      // Helper to convert entries to chart data
      const toChartData = (entries: [string, number][]): LineData[] => {
        return entries.map(([time, value]) => ({
          time: new Date(time).getTime() / 1000 as Time,
          value: value,
        }));
      };

      // Handle different indicator output formats
      if (indicator === 'macd') {
        // MACD returns histogram, signal, and macd line
        const histogram = values.histogram || {};
        const signal = values.signal || {};
        const macdLine = values.macd || {};
        
        const histogramData = toChartData(filterValidEntries(Object.entries(histogram)));
        const signalData = toChartData(filterValidEntries(Object.entries(signal)));
        const macdLineData = toChartData(filterValidEntries(Object.entries(macdLine)));
        
        return { 
          main: histogramData,
          additional: [signalData, macdLineData]
        };
      } else if (indicator === 'bollinger') {
        // Bollinger returns 3 lines - show all: middle (main), upper, lower
        const middle = values.middle || {};
        const upper = values.upper || {};
        const lower = values.lower || {};
        
        const middleData = toChartData(filterValidEntries(Object.entries(middle)));
        const upperData = toChartData(filterValidEntries(Object.entries(upper)));
        const lowerData = toChartData(filterValidEntries(Object.entries(lower)));
        
        console.log(`[convertToChartData] Bollinger bands: middle=${middleData.length}, upper=${upperData.length}, lower=${lowerData.length}`);
        
        return { 
          main: middleData,
          additional: [upperData, lowerData]
        };
      } else if (indicator === 'donchian' || indicator === 'keltner') {
        // Channel indicators with middle, upper, lower
        const middle = values.middle || {};
        const upper = values.upper || {};
        const lower = values.lower || {};
        
        return { 
          main: toChartData(filterValidEntries(Object.entries(middle))),
          additional: [
            toChartData(filterValidEntries(Object.entries(upper))),
            toChartData(filterValidEntries(Object.entries(lower)))
          ]
        };
      } else if (indicator === 'ichimoku') {
        // Ichimoku returns 5 lines - show tenkan for now
        const tenkan = values.tenkan || {};
        const validEntries = filterValidEntries(Object.entries(tenkan));
        return { main: toChartData(validEntries) };
      } else if (indicator === 'pivot_points' || indicator === 'pivot') {
        // Pivot Points returns pivot, s1-s3, r1-r3
        // Show pivot as main, with support and resistance as additional
        const pivot = values.pivot || {};
        const s1 = values.s1 || {};
        const s2 = values.s2 || {};
        const r1 = values.r1 || {};
        const r2 = values.r2 || {};
        
        return {
          main: toChartData(filterValidEntries(Object.entries(pivot))),
          additional: [
            toChartData(filterValidEntries(Object.entries(s1))),
            toChartData(filterValidEntries(Object.entries(s2))),
            toChartData(filterValidEntries(Object.entries(r1))),
            toChartData(filterValidEntries(Object.entries(r2)))
          ]
        };
      } else {
        // Standard format: {time: value}
        console.log(`[convertToChartData] Pre-access check:`, {
          hasValuesValues: !!(values && values.values),
          valuesValuesType: values && values.values ? typeof values.values : 'N/A',
          valuesKeys: values ? Object.keys(values) : [],
          valuesValuesKeys: values && values.values ? Object.keys(values.values).slice(0, 5) : [],
        });
        
        const dataValues = values.values || values;
        console.log(`[convertToChartData] Using dataValues:`, {
          dataValues: typeof dataValues,
          isObject: typeof dataValues === 'object',
          isNull: dataValues === null,
          isUndefined: dataValues === undefined,
          keys: typeof dataValues === 'object' && dataValues !== null ? Object.keys(dataValues).slice(0, 10) : [],
          firstEntry: typeof dataValues === 'object' && dataValues !== null ? Object.entries(dataValues)[0] : null,
          rawDataValues: dataValues, // Show actual object
        });
        
        if (!dataValues || typeof dataValues !== 'object' || Object.keys(dataValues).length === 0) {
          console.error(`[convertToChartData] dataValues is empty or invalid for ${indicator}:`, {
            dataValues,
            originalValues: values,
          });
          return { main: [] };
        }
        
        const validEntries = filterValidEntries(Object.entries(dataValues));
        
        const result = toChartData(validEntries);
        
        console.log(`[convertToChartData] Converted to ${result.length} chart points`);
        return { main: result };
      }
    },
    []
  );

  // Add indicator
  const addIndicator = useCallback(
    async (config: IndicatorConfig) => {
      if (!chart) {
        message.error('Chart not initialized');
        return;
      }

      setLoading(true);
      setError(null);

      try {
        // Check cache
        const cacheKey = getCacheKey(config.name, config.params);
        let indicatorData = cacheRef.current.get(cacheKey);

        // Fetch from API if not cached
        if (!indicatorData) {
          // Use last 6 months of data
          const end = new Date();
          const start = new Date();
          start.setMonth(start.getMonth() - 6);

          indicatorData = await apiRef.current.calculateIndicator(
            symbol,
            config.name,
            timeframe,
            config.params,
            start,
            end
          );

          console.log(`[useIndicators] Raw API response for ${config.name}:`, {
            fullResponse: indicatorData,
            indicator: indicatorData.indicator,
            valuesKeys: indicatorData.values ? Object.keys(indicatorData.values) : [],
            valuesValuesKeys: indicatorData.values?.values ? Object.keys(indicatorData.values.values) : [],
            firstValueSample: indicatorData.values?.values ? 
              Object.entries(indicatorData.values.values)[0] : null,
          });

          // Cache result
          cacheRef.current.set(cacheKey, indicatorData);
        }

        // Create series (returns { main, additional? })
        const seriesResult = createSeries(config);
        if (!seriesResult.main) {
          throw new Error('Failed to create chart series');
        }

        // Convert and set data (returns { main, additional? })
        const chartData = convertToChartData(indicatorData, config.name);
        console.log(`[useIndicators] Setting data for ${config.name}:`, {
          mainDataPoints: chartData.main.length,
          additionalDataSets: chartData.additional?.length || 0,
          firstPoint: chartData.main[0],
          lastPoint: chartData.main[chartData.main.length - 1],
        });
        
        // Set main series data
        seriesResult.main.setData(chartData.main);
        
        // Set additional series data (for multi-line indicators like Bollinger)
        if (seriesResult.additional && chartData.additional) {
          seriesResult.additional.forEach((series, index) => {
            if (chartData.additional && chartData.additional[index]) {
              series.setData(chartData.additional[index]);
              console.log(`[useIndicators] Set additional series ${index} with ${chartData.additional[index].length} points`);
            }
          });
        }
        
        console.log(`[useIndicators] Data set successfully for ${config.name}`);

        // Add to state
        setIndicators((prev) => [
          ...prev,
          {
            id: config.id,
            config,
            series: seriesResult.main,
            additionalSeries: seriesResult.additional,
            data: indicatorData,
          },
        ]);

        message.success(`Added ${config.displayName}`);
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to add indicator';
        setError(errorMsg);
        message.error(errorMsg);
        console.error('Failed to add indicator:', err);
      } finally {
        setLoading(false);
      }
    },
    [chart, symbol, timeframe, getCacheKey, createSeries, convertToChartData]
  );

  // Remove indicator
  const removeIndicator = useCallback(
    (id: string) => {
      let actuallyRemoved = false;
      
      setIndicators((prev) => {
        // Check if indicator exists before attempting removal
        const indicator = prev.find((ind) => ind.id === id);
        
        if (!indicator) {
          // Already removed in a previous call
          return prev;
        }
        
        // Mark that we're actually removing something
        actuallyRemoved = true;
        
        // Helper to safely remove a series
        const safeRemoveSeries = (series: ISeriesApi<'Line'> | ISeriesApi<'Histogram'> | null | undefined) => {
          if (!series || !chart) return;
          try {
            const isValidSeries = series && 
              typeof series === 'object' && 
              (typeof series.setData === 'function' || 
               typeof series.update === 'function' ||
               typeof series.applyOptions === 'function');
            
            if (isValidSeries) {
              chart.removeSeries(series);
            }
          } catch (_err: unknown) {
            // Silently handle errors
          }
        };
        
        // Remove main series
        safeRemoveSeries(indicator.series);
        
        // Remove additional series (for multi-line indicators)
        if (indicator.additionalSeries) {
          indicator.additionalSeries.forEach(safeRemoveSeries);
        }
        
        // Remove from state
        return prev.filter((ind) => ind.id !== id);
      });
      
      // Only show message if we actually removed something
      if (actuallyRemoved) {
        message.success('Indicator removed');
      }
    },
    [chart, message]
  );

  // Update indicator
  const updateIndicator = useCallback(
    async (id: string, updates: Partial<IndicatorConfig>) => {
      const indicator = indicators.find((ind) => ind.id === id);
      if (!indicator) return;

      // If just toggling enabled state
      if ('enabled' in updates && updates.enabled !== undefined) {
        setIndicators((prev) =>
          prev.map((ind) =>
            ind.id === id
              ? { ...ind, config: { ...ind.config, enabled: updates.enabled! } }
              : ind
          )
        );

        // Show/hide series
        if (indicator.series) {
          try {
            indicator.series.applyOptions({
              visible: updates.enabled,
            });
          } catch (err) {
            console.error('Failed to update series visibility:', err);
          }
        }
        return;
      }

      // If updating params, need to recalculate
      if (updates.params) {
        // Remove old series
        removeIndicator(id);

        // Add with new config
        const newConfig: IndicatorConfig = {
          ...indicator.config,
          ...updates,
          params: updates.params,
        };
        await addIndicator(newConfig);
      }
    },
    [indicators, addIndicator, removeIndicator]
  );

  // Clear all indicators
  const clearIndicators = useCallback(() => {
    setIndicators((currentIndicators) => {
      // Use functional update to access current state without dependency
      currentIndicators.forEach((indicator) => {
        // Remove main series
        if (indicator.series && chart) {
          try {
            chart.removeSeries(indicator.series);
          } catch (err) {
            console.error('Failed to remove series:', err);
          }
        }
        // Remove additional series
        if (indicator.additionalSeries && chart) {
          indicator.additionalSeries.forEach((series) => {
            try {
              chart.removeSeries(series);
            } catch (err) {
              console.error('Failed to remove additional series:', err);
            }
          });
        }
      });
      return [];
    });
    message.info('All indicators cleared');
  }, [chart]); // Only depend on chart, not indicators

  // Refresh all indicators
  const refreshIndicators = useCallback(async () => {
    // Clear cache
    cacheRef.current.clear();

    // Get current indicator configs before clearing
    const configs = indicators.map((ind) => ind.config);
    
    // Clear all indicators
    clearIndicators();

    // Reload all enabled indicators
    for (const config of configs) {
      if (config.enabled) {
        await addIndicator(config);
      }
    }
  }, [indicators, clearIndicators, addIndicator]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearIndicators();
    };
  }, [clearIndicators]);

  return {
    indicators,
    loading,
    error,
    addIndicator,
    removeIndicator,
    updateIndicator,
    clearIndicators,
    refreshIndicators,
  };
};

export default useIndicators;
