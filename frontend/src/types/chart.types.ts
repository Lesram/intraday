/**
 * Chart Types and Interfaces
 * Type definitions for charting functionality
 */

import type { Time } from 'lightweight-charts';

/**
 * Timeframe options for charts
 */
export type Timeframe = '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1D' | '1W' | '1M';

/**
 * Chart types
 */
export type ChartType = 'candlestick' | 'line' | 'area' | 'bar' | 'baseline';

/**
 * OHLCV Bar data
 */
export interface Bar {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * Lightweight Charts candlestick data
 */
export interface CandlestickData {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
}

/**
 * Volume histogram data
 */
export interface VolumeData {
  time: Time;
  value: number;
  color?: string;
}

/**
 * Line series data
 */
export interface LineData {
  time: Time;
  value: number;
}

/**
 * Chart indicator configuration
 */
export interface IndicatorConfig {
  id: string;
  name: string;
  type: 'overlay' | 'panel';
  enabled: boolean;
  color: string;
  lineWidth: number;
  params: Record<string, number | string>;
}

/**
 * Technical indicators
 */
export type IndicatorType = 
  | 'SMA'
  | 'EMA'
  | 'RSI'
  | 'MACD'
  | 'BB'  // Bollinger Bands
  | 'VWAP'
  | 'ATR'
  | 'STOCH'
  | 'ADX'
  | 'OBV';

/**
 * Chart drawing tools
 */
export type DrawingTool = 
  | 'trendline'
  | 'horizontal'
  | 'vertical'
  | 'fibonacci'
  | 'rectangle'
  | 'circle'
  | 'text';

/**
 * Drawing object
 */
export interface Drawing {
  id: string;
  type: DrawingTool;
  points: Array<{ time: Time; price: number }>;
  color: string;
  lineWidth: number;
  text?: string;
}

/**
 * Chart state
 */
export interface ChartState {
  symbol: string;
  timeframe: Timeframe;
  chartType: ChartType;
  indicators: IndicatorConfig[];
  drawings: Drawing[];
  autoScale: boolean;
  showGrid: boolean;
  showCrosshair: boolean;
  showVolume: boolean;
}

/**
 * Interface for series API methods we need
 */
export interface ISeriesApiWithData {
  setData(data: unknown[]): void;
  update(data: unknown): void;
}

/**
 * Chart series references
 */
export interface ChartSeries {
  candlestick?: ISeriesApiWithData; // ISeriesApi
  volume?: ISeriesApiWithData; // ISeriesApi
  indicators: Map<string, ISeriesApiWithData>; // Map<string, ISeriesApi>
}

/**
 * Historical bars request
 */
export interface BarsRequest {
  symbol: string;
  timeframe: Timeframe;
  start?: string;
  end?: string;
  limit?: number;
}

/**
 * Historical bars response
 */
export interface BarsResponse {
  symbol: string;
  timeframe: Timeframe;
  bars: Bar[];
  count: number;
}

/**
 * Chart theme colors
 */
export interface ChartTheme {
  background: string;
  textColor: string;
  gridColor: string;
  upColor: string;
  downColor: string;
  borderUpColor: string;
  borderDownColor: string;
  wickUpColor: string;
  wickDownColor: string;
  volumeUpColor: string;
  volumeDownColor: string;
}

/**
 * Chart options
 */
export interface ChartOptions {
  width?: number;
  height?: number;
  theme?: ChartTheme;
  autoScale?: boolean;
  showGrid?: boolean;
  showCrosshair?: boolean;
  showTimeScale?: boolean;
  showPriceScale?: boolean;
}

/**
 * Indicator preset
 */
export interface IndicatorPreset {
  name: string;
  indicators: Array<{
    type: IndicatorType;
    params: Record<string, number | string>;
    color: string;
  }>;
}
