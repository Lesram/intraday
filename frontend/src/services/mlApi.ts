/**
 * ML Models API Service
 * API calls for model management, training, predictions, and monitoring
 * Phase 6 Implementation
 */

import { apiClient } from './api';
import type {
  ModelInfo,
  ModelListResponse,
  ModelTrainingRequest,
  TrainingResponse,
  TrainingProgress,
  PredictionRequest,
  PredictionResponse,
  FeatureImportanceResponse,
  ModelComparisonRequest,
  ModelComparisonResult,
  ModelHealthResponse,
  ModelVersionInfo,
  ModelActivationRequest,
  MonitoringRunResponse,
  MonitoringSnapshotListResponse,
  RetrainIfNeededRequest,
  RetrainIfNeededResponse,
  LifecycleSummaryResponse,
  LifecycleRunResponse,
  TradingExecutionMode,
  TradingExecutionModeResponse,
} from '../types/ml';

/**
 * ML Models API Client
 * Provides type-safe methods for all ML model endpoints
 */
export const mlApi = {
  // ===========================
  // MODEL REGISTRY
  // ===========================

  /**
   * List all models with pagination and filtering
   * @param params - Query parameters (page, page_size, active_only, model_type)
   */
  listModels: async (params?: {
    page?: number;
    page_size?: number;
    active_only?: boolean;
    model_type?: string;
  }): Promise<ModelListResponse> => {
    const response = await apiClient.get('/models', { params });
    return response.data;
  },

  /**
   * Get detailed information about a specific model
   * @param modelId - UUID of the model
   */
  getModel: async (modelId: string): Promise<ModelInfo> => {
    const response = await apiClient.get(`/models/${modelId}`);
    return response.data;
  },

  /**
   * Delete a model (admin only)
   * @param modelId - UUID of the model to delete
   */
  deleteModel: async (modelId: string): Promise<void> => {
    await apiClient.delete(`/models/${modelId}`);
  },

  /**
   * Activate or deactivate a model (admin only)
   * @param modelId - UUID of the model
   * @param request - Activation request with active flag
   */
  activateModel: async (
    modelId: string,
    request: ModelActivationRequest
  ): Promise<ModelInfo> => {
    const response = await apiClient.post(`/models/${modelId}/activate`, request);
    return response.data;
  },

  // ===========================
  // MODEL TRAINING
  // ===========================

  /**
   * Start training a new model (admin only)
   * @param config - Training configuration
   */
  startTraining: async (config: ModelTrainingRequest): Promise<TrainingResponse> => {
    const response = await apiClient.post('/models/train', config);
    return response.data;
  },

  /**
   * Get training progress for a specific job
   * @param jobId - Training job ID
   */
  getTrainingStatus: async (jobId: string): Promise<TrainingProgress> => {
    const response = await apiClient.get(`/models/training/${jobId}`);
    return response.data;
  },

  /**
   * Cancel a training job (admin only)
   * @param jobId - Training job ID
   */
  cancelTraining: async (jobId: string): Promise<void> => {
    await apiClient.post(`/models/training/${jobId}/cancel`);
  },

  // ===========================
  // PREDICTIONS
  // ===========================

  /**
   * Get predictions for a symbol
   * @param request - Prediction request with symbol and optional model_id
   */
  predict: async (request: PredictionRequest): Promise<PredictionResponse> => {
    const response = await apiClient.post('/models/predict', request);
    return response.data;
  },

  /**
   * Get batch predictions for multiple symbols
   * @param requests - Array of prediction requests
   */
  batchPredict: async (
    requests: PredictionRequest[]
  ): Promise<PredictionResponse[]> => {
    const response = await apiClient.post('/models/predict/batch', { requests });
    return response.data;
  },

  // ===========================
  // MODEL ANALYSIS
  // ===========================

  /**
   * Get feature importance for a model
   * @param modelId - UUID of the model
   */
  getFeatureImportance: async (modelId: string): Promise<FeatureImportanceResponse> => {
    const response = await apiClient.get(`/models/${modelId}/features`);
    return response.data;
  },

  /**
   * Compare multiple models
   * @param request - Comparison request with model IDs
   */
  compareModels: async (
    request: ModelComparisonRequest
  ): Promise<ModelComparisonResult> => {
    const response = await apiClient.post('/models/compare', request);
    return response.data;
  },

  /**
   * Get model health and drift metrics
   * @param modelId - UUID of the model
   */
  getModelHealth: async (modelId: string): Promise<ModelHealthResponse> => {
    const response = await apiClient.get(`/models/${modelId}/health`);
    return response.data;
  },

  // ===========================
  // MONITORING & RETRAIN
  // ===========================

  listMonitoringSnapshots: async (
    modelId: string,
    params?: { limit?: number }
  ): Promise<MonitoringSnapshotListResponse> => {
    const response = await apiClient.get(`/models/${modelId}/monitor/snapshots`, { params });
    return response.data;
  },

  runMonitoring: async (
    modelId: string,
    params?: { lookback_days?: number }
  ): Promise<MonitoringRunResponse> => {
    const response = await apiClient.post(`/models/${modelId}/monitor/run`, null, { params });
    return response.data;
  },

  retrainIfNeeded: async (
    modelId: string,
    request: RetrainIfNeededRequest
  ): Promise<RetrainIfNeededResponse> => {
    const response = await apiClient.post(`/models/${modelId}/retrain-if-needed`, request);
    return response.data;
  },

  // ===========================
  // LIFECYCLE (SCHEDULE + DASHBOARD)
  // ===========================

  getLifecycleSummary: async (): Promise<LifecycleSummaryResponse> => {
    const response = await apiClient.get('/models/lifecycle/summary');
    return response.data;
  },

  runDailyMonitoringJob: async (params?: { lookback_days?: number }): Promise<LifecycleRunResponse> => {
    const response = await apiClient.post('/models/lifecycle/run/daily-monitoring', null, { params });
    return response.data;
  },

  runWeeklyRetrainJob: async (params?: {
    lookback_days?: number;
    min_return_drop?: number;
    psi_threshold?: number;
  }): Promise<LifecycleRunResponse> => {
    const response = await apiClient.post('/models/lifecycle/run/weekly-retrain', null, { params });
    return response.data;
  },

  runMonthlyReviewJob: async (): Promise<LifecycleRunResponse> => {
    const response = await apiClient.post('/models/lifecycle/run/monthly-review');
    return response.data;
  },

  // ===========================
  // ADMIN: TRADING CONTROLS
  // ===========================

  getTradingExecutionMode: async (): Promise<TradingExecutionModeResponse> => {
    const response = await apiClient.get('/admin/trading/execution-mode');
    return response.data;
  },

  setTradingExecutionMode: async (mode: TradingExecutionMode): Promise<TradingExecutionModeResponse> => {
    const response = await apiClient.put('/admin/trading/execution-mode', { mode });
    return response.data;
  },

  clearTradingExecutionModeOverride: async (): Promise<TradingExecutionModeResponse> => {
    const response = await apiClient.delete('/admin/trading/execution-mode');
    return response.data;
  },

  // ===========================
  // VERSION HISTORY
  // ===========================

  /**
   * Get version history for a model name
   * @param modelName - Name of the model
   */
  getVersionHistory: async (modelName: string): Promise<ModelVersionInfo[]> => {
    const response = await apiClient.get(`/models/${modelName}/versions`);
    return response.data;
  },

  // ===========================
  // STATS & SUMMARY
  // ===========================

  /**
   * Get model statistics summary
   */
  getModelStats: async (): Promise<{
    total_models: number;
    active_models: number;
    training_jobs: number;
    avg_accuracy: number;
    recent_predictions: number;
  }> => {
    const response = await apiClient.get('/models/stats');
    return response.data;
  },
};

// ===========================
// REACT QUERY HOOKS
// ===========================

/**
 * React Query hook keys for ML models
 * Used for cache invalidation and refetching
 */
export const mlQueryKeys = {
  all: ['ml-models'] as const,
  lists: () => [...mlQueryKeys.all, 'list'] as const,
  list: (params?: unknown) => [...mlQueryKeys.lists(), params] as const,
  details: () => [...mlQueryKeys.all, 'detail'] as const,
  detail: (id: string) => [...mlQueryKeys.details(), id] as const,
  training: () => [...mlQueryKeys.all, 'training'] as const,
  trainingJob: (jobId: string) => [...mlQueryKeys.training(), jobId] as const,
  predictions: () => [...mlQueryKeys.all, 'predictions'] as const,
  prediction: (symbol: string) => [...mlQueryKeys.predictions(), symbol] as const,
  features: (modelId: string) => [...mlQueryKeys.all, 'features', modelId] as const,
  health: (modelId: string) => [...mlQueryKeys.all, 'health', modelId] as const,
  monitoring: (modelId: string) => [...mlQueryKeys.all, 'monitoring', modelId] as const,
  monitoringSnapshots: (modelId: string, params?: unknown) =>
    [...mlQueryKeys.monitoring(modelId), 'snapshots', params] as const,
  lifecycle: () => [...mlQueryKeys.all, 'lifecycle'] as const,
  lifecycleSummary: () => [...mlQueryKeys.lifecycle(), 'summary'] as const,
  tradingExecutionMode: () => [...mlQueryKeys.all, 'admin', 'trading', 'execution-mode'] as const,
  versions: (modelName: string) => [...mlQueryKeys.all, 'versions', modelName] as const,
  stats: () => [...mlQueryKeys.all, 'stats'] as const,
};

/**
 * Query options for React Query
 */
export const mlQueryOptions = {
  // Models list - refresh every 30 seconds
  models: {
    staleTime: 30000,
    cacheTime: 300000,
    refetchInterval: 30000,
  },
  // Model detail - refresh every 10 seconds
  modelDetail: {
    staleTime: 10000,
    cacheTime: 300000,
  },
  // Training progress - refresh every 2 seconds (active polling)
  training: {
    staleTime: 0,
    cacheTime: 60000,
    refetchInterval: 2000,
  },
  // Predictions - cache for 5 minutes
  predictions: {
    staleTime: 300000,
    cacheTime: 600000,
  },
  // Model health - refresh every 60 seconds
  health: {
    staleTime: 60000,
    cacheTime: 300000,
  },
  // Stats - refresh every 15 seconds
  stats: {
    staleTime: 15000,
    cacheTime: 300000,
    refetchInterval: 15000,
  },
};

/**
 * Error handling utilities
 */
export const mlErrorMessages = {
  listModels: 'Failed to load models',
  getModel: 'Failed to load model details',
  deleteModel: 'Failed to delete model',
  activateModel: 'Failed to activate/deactivate model',
  startTraining: 'Failed to start training',
  getTrainingStatus: 'Failed to load training status',
  cancelTraining: 'Failed to cancel training',
  predict: 'Failed to get predictions',
  getFeatureImportance: 'Failed to load feature importance',
  compareModels: 'Failed to compare models',
  getModelHealth: 'Failed to load model health',
  getVersionHistory: 'Failed to load version history',
  getModelStats: 'Failed to load model statistics',
};

/**
 * Helper function to handle API errors
 */
export const handleMlApiError = (error: unknown, operation: keyof typeof mlErrorMessages): string => {
  console.error(`${operation} error:`, error);
  
  if (error && typeof error === 'object' && 'response' in error) {
    const axiosError = error as { response?: { data?: { detail?: string } } };
    if (axiosError.response?.data?.detail) {
      return axiosError.response.data.detail;
    }
  }
  
  return mlErrorMessages[operation];
};

/**
 * Type guard to check if a model is currently training
 */
export const isModelTraining = (model: ModelInfo): boolean => {
  return model.status === 'training';
};

/**
 * Type guard to check if a model is active
 */
export const isModelActive = (model: ModelInfo): boolean => {
  return model.active === true;
};

/**
 * Helper to format model accuracy as percentage
 */
export const formatAccuracy = (accuracy: number): string => {
  return `${(accuracy * 100).toFixed(2)}%`;
};

/**
 * Helper to get model status color
 */
export const getModelStatusColor = (
  status: string
): 'success' | 'processing' | 'warning' | 'error' | 'default' => {
  const statusMap: Record<string, 'success' | 'processing' | 'warning' | 'error' | 'default'> = {
    active: 'success',
    training: 'processing',
    deployed: 'success',
    failed: 'error',
    archived: 'default',
    pending: 'warning',
  };
  return statusMap[status.toLowerCase()] || 'default';
};

/**
 * Helper to format training time
 */
export const formatTrainingTime = (seconds: number): string => {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
};
