/**
 * useDrawingTools Hook
 * 
 * Manages chart drawing tools: creation, editing, persistence, and rendering.
 * 
 * Features:
 * - Handle chart click events for drawing creation
 * - Manage drawing state (active drawings, drawing mode)
 * - API integration (save/load/delete drawings)
 * - Undo/redo functionality
 * - Chart rendering of drawings
 * 
 * Phase 7 - Market Data & Charting
 * Created: October 16, 2025
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { message } from 'antd';
import { LineSeries, type IChartApi, type ISeriesApi, type MouseEventParams, type Time } from 'lightweight-charts';
import type { Drawing, DrawingType, DrawingStyle, Point } from '../components/market/DrawingTools';
import { apiClient } from '../services/api';

// Extended chart interface for methods not in type definitions
interface ExtendedChartApi extends IChartApi {
  subscribeClick: (handler: (params: MouseEventParams) => void) => void;
  unsubscribeClick: (handler: (params: MouseEventParams) => void) => void;
}

// ============================================================================
// TYPES
// ============================================================================

interface UseDrawingToolsProps {
  chart: IChartApi | null;
  symbol: string;
  timeframe: string;
}

interface UseDrawingToolsReturn {
  drawings: Drawing[];
  selectedTool: DrawingType | null;
  style: DrawingStyle;
  loading: boolean;
  error: string | null;
  selectTool: (tool: DrawingType | null) => void;
  updateStyle: (style: Partial<DrawingStyle>) => void;
  saveDrawings: () => Promise<void>;
  loadDrawings: () => Promise<void>;
  clearDrawings: () => void;
  undoLastDrawing: () => void;
  deleteDrawing: (id: string) => void;
}

// ============================================================================
// API CLIENT
// ============================================================================

class DrawingsAPI {
  async getDrawings(symbol: string, timeframe: string): Promise<Drawing[]> {
    try {
      const response = await apiClient.get(`/drawings/${symbol}?timeframe=${timeframe}`);
      return response.data;
    } catch (error: unknown) {
      // Silently handle 401 errors (user not logged in)
      const axiosError = error as { response?: { status?: number } };
      if (axiosError?.response?.status === 401) {
        return [];
      }
      throw error;
    }
  }

  async createDrawing(drawing: Omit<Drawing, 'id'>): Promise<Drawing> {
    const response = await apiClient.post('/drawings/', drawing);
    return response.data;
  }

  async deleteDrawing(id: string): Promise<void> {
    await apiClient.delete(`/drawings/${id}`);
  }

  async deleteAllDrawings(symbol: string, timeframe: string): Promise<void> {
    await apiClient.delete(`/drawings/symbol/${symbol}?timeframe=${timeframe}`);
  }
}

// ============================================================================
// HOOK
// ============================================================================

export const useDrawingTools = ({
  chart,
  symbol,
  timeframe,
}: UseDrawingToolsProps): UseDrawingToolsReturn => {
  // State
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [selectedTool, setSelectedTool] = useState<DrawingType | null>(null);
  const [style, setStyle] = useState<DrawingStyle>({
    color: '#2962FF',
    lineWidth: 2,
    lineStyle: 'solid',
    fillColor: '#2962FF',
    fillOpacity: 0.2,
    textSize: 12,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Refs
  const apiRef = useRef(new DrawingsAPI());
  const drawingPointsRef = useRef<Point[]>([]);
  const chartSeriesRef = useRef<Map<string, unknown>>(new Map());
  const drawingHistoryRef = useRef<Drawing[]>([]);

  // Convert chart coordinates to point
  const chartPointToPoint = useCallback((params: MouseEventParams): Point | null => {
    if (!params.time || params.point === undefined) return null;

    // Get price from first series in seriesData map
    let priceData: { close?: number; value?: number } | undefined;
    if (params.seriesData && params.seriesData.size > 0) {
      const firstEntry = params.seriesData.values().next().value;
      priceData = firstEntry as { close?: number; value?: number };
    }
    if (!priceData) return null;

    return {
      time: params.time as number,
      price: priceData.close || priceData.value || 0,
    };
  }, []);

  // Render drawing on chart
  const renderDrawing = useCallback(
    (drawing: Drawing) => {
      if (!chart) return;

      try {
        const { type, points, style: drawingStyle } = drawing;

        switch (type) {
          case 'trendline': {
            if (points.length !== 2) return;
            
            // Create line series for trendline
            const series = chart.addSeries(LineSeries, {
              color: drawingStyle.color,
              lineWidth: (drawingStyle.lineWidth as 1 | 2 | 3 | 4) || 2,
              lineStyle: drawingStyle.lineStyle === 'dashed' ? 1 : 
                        drawingStyle.lineStyle === 'dotted' ? 2 : 0,
              priceScaleId: 'right',
            });

            // Calculate line points
            const data = [
              { time: points[0].time as Time, value: points[0].price },
              { time: points[1].time as Time, value: points[1].price },
            ];
            series.setData(data);

            chartSeriesRef.current.set(drawing.id, series);
            break;
          }

          case 'horizontal': {
            if (points.length !== 1) return;

            // Create horizontal price line
            const priceLine = {
              price: points[0].price,
              color: drawingStyle.color,
              lineWidth: drawingStyle.lineWidth,
              lineStyle: drawingStyle.lineStyle === 'dashed' ? 1 : 
                        drawingStyle.lineStyle === 'dotted' ? 2 : 0,
              axisLabelVisible: true,
              title: 'H',
            };

            // Store price line reference
            chartSeriesRef.current.set(drawing.id, priceLine);
            break;
          }

          case 'vertical': {
            // Vertical lines require custom rendering (not natively supported)
            // TODO: Implement custom vertical line rendering
            console.warn('Vertical lines not yet implemented');
            break;
          }

          case 'fibonacci': {
            if (points.length !== 2) return;

            // Calculate Fibonacci levels
            const diff = points[1].price - points[0].price;
            const levels = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0];
            const fibSeries: ISeriesApi<'Line'>[] = [];

            levels.forEach((level) => {
              const price = points[0].price + diff * level;
              const series = chart.addSeries(LineSeries, {
                color: drawingStyle.color,
                lineWidth: 1,
                lineStyle: 1, // dashed
                priceScaleId: 'right',
              });

              const data = [
                { time: points[0].time as Time, value: price },
                { time: points[1].time as Time, value: price },
              ];
              series.setData(data);

              fibSeries.push(series);
            });

            chartSeriesRef.current.set(drawing.id, fibSeries);
            break;
          }

          case 'rectangle':
          case 'ellipse': {
            // Shapes require custom rendering
            // TODO: Implement custom shape rendering
            console.warn(`${type} not yet fully implemented`);
            break;
          }

          case 'text': {
            // Text annotations require custom markers
            // TODO: Implement text markers
            console.warn('Text annotations not yet implemented');
            break;
          }

          default:
            console.warn(`Unknown drawing type: ${type}`);
        }
      } catch (err) {
        console.error('Failed to render drawing:', err);
      }
    },
    [chart]
  );

  // Remove drawing from chart
  const removeDrawingFromChart = useCallback(
    (drawingId: string) => {
      if (!chart) return;

      try {
        const series = chartSeriesRef.current.get(drawingId);
        if (series) {
          if (Array.isArray(series)) {
            // Multiple series (e.g., Fibonacci)
            series.forEach((s) => {
              try {
                chart.removeSeries(s as ISeriesApi<'Line'>);
              } catch (err) {
                console.error('Failed to remove series:', err);
              }
            });
          } else {
            // Single series
            try {
              chart.removeSeries(series as ISeriesApi<'Line'>);
            } catch (err) {
              console.error('Failed to remove series:', err);
            }
          }
          chartSeriesRef.current.delete(drawingId);
        }
      } catch (err) {
        console.error('Failed to remove drawing from chart:', err);
      }
    },
    [chart]
  );

  // Handle chart click for drawing
  const handleChartClick = useCallback(
    (params: MouseEventParams) => {
      if (!selectedTool || !chart) return;

      const point = chartPointToPoint(params);
      if (!point) return;

      drawingPointsRef.current.push(point);

      // Determine if drawing is complete
      const requiredPoints: Record<DrawingType, number> = {
        trendline: 2,
        horizontal: 1,
        vertical: 1,
        fibonacci: 2,
        rectangle: 2,
        ellipse: 2,
        text: 1,
      };

      const required = requiredPoints[selectedTool];
      
      if (drawingPointsRef.current.length >= required) {
        // Create drawing
        const newDrawing: Omit<Drawing, 'id'> = {
          symbol,
          type: selectedTool,
          points: [...drawingPointsRef.current],
          style,
          timeframe,
        };

        // Add to state (with temporary ID)
        const tempDrawing: Drawing = {
          ...newDrawing,
          id: `temp_${Date.now()}`,
        };

        setDrawings((prev) => [...prev, tempDrawing]);
        drawingHistoryRef.current.push(tempDrawing);

        // Render on chart
        renderDrawing(tempDrawing);

        // Reset points
        drawingPointsRef.current = [];

        message.success(`${selectedTool} created`);

        // Auto-deselect tool after single-point tools
        if (required === 1) {
          setSelectedTool(null);
        }
      } else {
        // Show feedback for multi-point tools
        message.info(`Click ${required - drawingPointsRef.current.length} more point(s)`);
      }
    },
    [selectedTool, chart, symbol, timeframe, style, chartPointToPoint, renderDrawing]
  );

  // Subscribe to chart clicks
  useEffect(() => {
    if (!chart) return;

    const clickHandler = (params: MouseEventParams) => {
      handleChartClick(params);
    };

    const extendedChart = chart as ExtendedChartApi;
    extendedChart.subscribeClick(clickHandler);

    return () => {
      try {
        extendedChart.unsubscribeClick(clickHandler);
      } catch (_err: unknown) {
        // Ignore unsubscribe errors
      }
    };
  }, [chart, handleChartClick]);

  // Select tool
  const selectTool = useCallback((tool: DrawingType | null) => {
    setSelectedTool(tool);
    drawingPointsRef.current = []; // Reset points when changing tool
    
    if (tool) {
      message.info(`${tool} tool selected. Click on chart to draw.`);
    }
  }, []);

  // Update style
  const updateStyle = useCallback((updates: Partial<DrawingStyle>) => {
    setStyle((prev) => ({ ...prev, ...updates }));
  }, []);

  // Save drawings to backend
  const saveDrawings = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Filter out temporary drawings and save to backend
      const unsavedDrawings = drawings.filter((d) => d.id.startsWith('temp_'));

      for (const drawing of unsavedDrawings) {
        const { id: _id, ...drawingData } = drawing;
        await apiRef.current.createDrawing(drawingData);
      }

      // Reload all drawings from backend to get proper IDs
      await loadDrawings();

      message.success(`Saved ${unsavedDrawings.length} drawing(s)`);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to save drawings';
      setError(errorMsg);
      message.error(errorMsg);
      console.error('Save drawings error:', err);
    } finally {
      setLoading(false);
    }
  }, [drawings]);

  // Load drawings from backend
  const loadDrawings = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const loadedDrawings = await apiRef.current.getDrawings(symbol, timeframe);
      
      // Clear existing chart drawings
      chartSeriesRef.current.forEach((_, id) => {
        removeDrawingFromChart(id);
      });

      // Render loaded drawings
      loadedDrawings.forEach((drawing) => {
        renderDrawing(drawing);
      });

      setDrawings(loadedDrawings);
      drawingHistoryRef.current = [...loadedDrawings];
    } catch (err) {
      // Silently handle auth errors (user not logged in)
      const errorMsg = err instanceof Error ? err.message : 'Failed to load drawings';
      if (!errorMsg.includes('Authentication')) {
        setError(errorMsg);
        console.error('Load drawings error:', err);
      }
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe, renderDrawing, removeDrawingFromChart]);

  // Clear all drawings
  const clearDrawings = useCallback(() => {
    // Remove from chart
    chartSeriesRef.current.forEach((_, id) => {
      removeDrawingFromChart(id);
    });

    // Clear state
    setDrawings([]);
    drawingHistoryRef.current = [];
    drawingPointsRef.current = [];
  }, [removeDrawingFromChart]);

  // Undo last drawing
  const undoLastDrawing = useCallback(() => {
    if (drawings.length === 0) {
      message.warning('No drawings to undo');
      return;
    }

    const lastDrawing = drawings[drawings.length - 1];
    
    // Remove from chart
    removeDrawingFromChart(lastDrawing.id);

    // Remove from state
    setDrawings((prev) => prev.slice(0, -1));
    drawingHistoryRef.current = drawingHistoryRef.current.slice(0, -1);
  }, [drawings, removeDrawingFromChart]);

  // Delete specific drawing
  const deleteDrawing = useCallback(
    async (id: string) => {
      try {
        // If it's a saved drawing (not temporary), delete from backend
        if (!id.startsWith('temp_')) {
          await apiRef.current.deleteDrawing(id);
        }

        // Remove from chart
        removeDrawingFromChart(id);

        // Remove from state
        setDrawings((prev) => prev.filter((d) => d.id !== id));
        drawingHistoryRef.current = drawingHistoryRef.current.filter((d) => d.id !== id);

        message.success('Drawing deleted');
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to delete drawing';
        message.error(errorMsg);
        console.error('Delete drawing error:', err);
      }
    },
    [removeDrawingFromChart]
  );

  // Load drawings on mount and when symbol/timeframe changes
  useEffect(() => {
    if (chart && symbol && timeframe) {
      loadDrawings();
    }
  }, [chart, symbol, timeframe]); // Intentionally not including loadDrawings to avoid loops

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearDrawings();
    };
  }, []); // Intentionally empty to only run on unmount

  return {
    drawings,
    selectedTool,
    style,
    loading,
    error,
    selectTool,
    updateStyle,
    saveDrawings,
    loadDrawings,
    clearDrawings,
    undoLastDrawing,
    deleteDrawing,
  };
};

export default useDrawingTools;
