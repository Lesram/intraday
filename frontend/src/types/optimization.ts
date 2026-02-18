export interface OptimizationRun {
  id: string;
  name: string;
  created_at: string;
  source_log?: string | null;
  symbols: string[];
  range?: Record<string, unknown> | null;
  holdout?: Record<string, unknown> | null;
  strategy_type: string;
  parameters: Record<string, unknown>;
  origin: string;
}

export interface OptimizationStrategyCreate {
  name?: string;
  description?: string;
  strategy_type?: string;
  symbols?: string[];
}
