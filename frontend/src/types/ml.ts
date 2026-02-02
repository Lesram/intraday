/**
 * ML Models TypeScript Type Definitions
 * Phase 6 Implementation
 */

export const ModelType = {
  ENSEMBLE: 'ensemble',
  LSTM: 'lstm',
  XGBOOST: 'xgboost',
  RANDOM_FOREST: 'random_forest',
  REGRESSION: 'regression',
  CLASSIFICATION: 'classification',
} as const;

export type ModelType = typeof ModelType[keyof typeof ModelType];

export const ModelStatus = {
  TRAINING: 'training',
  READY: 'ready',
  FAILED: 'failed',
  INACTIVE: 'inactive',
  DEPRECATED: 'deprecated',
} as const;

export type ModelStatus = typeof ModelStatus[keyof typeof ModelStatus];

export const TrainingStatus = {
  PENDING: 'pending',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const;

export type TrainingStatus = typeof TrainingStatus[keyof typeof TrainingStatus];

export interface ModelMetrics {
  // Classification metrics
  accuracy?: number;
  precision?: number;
  recall?: number;
  f1_score?: number;
  
  // Regression metrics
  mae?: number;
  rmse?: number;
  r2_score?: number;
  mape?: number;
  
  // Performance metrics
  training_time?: number;
  inference_time?: number;
  
  // Custom metrics
  custom_metrics?: Record<string, unknown>;
}

export interface ModelInfo {
  id: string;
  name: string;
  version: string;
  model_type: ModelType;
  status: ModelStatus;
  active: boolean;
  path: string;
  trained_at: string;
  created_at: string;
  updated_at: string;
  metrics: ModelMetrics;
  features: string[];
  symbols: string[];
  hyperparameters: Record<string, unknown>;
  prediction_count: number;
  avg_confidence?: number;
}

export interface ModelListResponse {
  models: ModelInfo[];
  total: number;
  page: number;
  page_size: number;
}

export interface ModelTrainingRequest {
  model_type: ModelType;
  model_name: string;
  features?: string[];
  symbols?: string[];
  lookback_days?: number;
  test_size?: number;
  hyperparameters?: Record<string, unknown>;
  retrain?: boolean;
}

export interface TrainingProgress {
  training_id: string;
  status: TrainingStatus;
  progress: number;
  current_epoch?: number;
  total_epochs?: number;
  current_metrics: Record<string, number>;
  eta_seconds?: number;
  started_at: string;
  message?: string;
}

export interface TrainingResponse {
  training_id: string;
  model_name: string;
  status: TrainingStatus;
  message: string;
  started_at: string;
}

export interface PredictionRequest {
  symbol: string;
  model_id?: string;
  data?: Record<string, unknown>;
}

export interface PredictionResponse {
  symbol: string;
  prediction: number;
  confidence: number;
  model_id: string;
  model_name: string;
  features_used: string[];
  timestamp: string;
}

export type TradingExecutionMode = 'execute' | 'shadow' | 'dry_run';

export interface TradingExecutionModeResponse {
  mode: TradingExecutionMode;
  source: 'env' | 'override';
  default_mode: TradingExecutionMode;
  overridden: boolean;
  override_set_by?: string | null;
  override_set_at?: string | null;
  allowed_modes: TradingExecutionMode[];
  alpaca_paper: boolean;
  alpaca_base_url: string;
  use_mock_broker: boolean;
}

export interface FeatureImportance {
  feature_name: string;
  importance: number;
  rank: number;
}

export interface FeatureImportanceResponse {
  model_id: string;
  model_name: string;
  features: FeatureImportance[];
  generated_at: string;
}

export interface DriftMetrics {
  psi_score: number;
  drift_detected: boolean;
  affected_features: string[];
  drift_severity: 'low' | 'medium' | 'high';
  last_checked: string;
}

export interface ModelHealthResponse {
  model_id: string;
  model_name: string;
  health_score: number;
  status: ModelStatus;
  drift_metrics?: DriftMetrics;
  recent_performance: Record<string, number>;
  issues: string[];
  recommendations: string[];
  last_checked: string;
}

export interface MonitoringSnapshot {
  id: string;
  model_id?: string;
  model_name: string;
  model_version: string;
  window_start: string;
  window_end: string;
  metrics: Record<string, unknown>;
  drift: Record<string, unknown>;
  created_at: string;
}

export interface MonitoringSnapshotListResponse {
  model_id: string;
  snapshots: MonitoringSnapshot[];
}

export interface MonitoringRunResponse {
  snapshot: MonitoringSnapshot;
}

export interface RetrainIfNeededRequest {
  lookback_days?: number;
  min_return_drop?: number;
  psi_threshold?: number;
}

export interface RetrainIfNeededResponse {
  should_retrain: boolean;
  reasons: string[];
  training_id?: string;
  snapshot?: MonitoringSnapshot;
}

export interface LifecycleModelSummary {
  model_id: string;
  model_name: string;
  model_version: string;
  active: boolean;
  last_snapshot?: MonitoringSnapshot;
  last_retrain_decision?: Record<string, unknown>;
}

export interface LifecycleSummaryResponse {
  scheduler_enabled: boolean;
  scheduler_state: Record<string, unknown>;
  active_models: LifecycleModelSummary[];
  last_promotion_review?: Record<string, unknown>;
}

export interface LifecycleRunResponse {
  ok: boolean;
  message: string;
  details: Record<string, unknown>;
}

export interface ModelComparisonRequest {
  model_ids: string[];
  metric?: string;
}

export interface ModelComparisonResult {
  models: ModelInfo[];
  best_model_id: string;
  comparison_metric: string;
  metrics_comparison: Record<string, Record<string, number>>;
  recommendations: string[];
}

export interface ModelVersionInfo {
  version: string;
  trained_at: string;
  metrics: ModelMetrics;
  active: boolean;
  notes?: string;
}

export interface ModelVersionHistoryResponse {
  model_name: string;
  versions: ModelVersionInfo[];
  current_version: string;
}

// Model activation request
export interface ModelActivationRequest {
  active: boolean;
}

// Table filters
export interface ModelFilters {
  status?: ModelStatus;
  model_type?: ModelType;
  active_only?: boolean;
  search?: string;
}

// UI State
export interface MLModelsState {
  selectedModelId?: string;
  trainingInProgress: boolean;
  activeTab: string;
}
