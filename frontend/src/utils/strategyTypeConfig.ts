/**
 * Strategy Type Configuration
 * Icons, labels, and descriptions for each strategy type
 * NOTE: These must match backend VALID_STRATEGY_TYPES in strategy_service.py
 */

import type { StrategyType } from '@/types/strategy';

export interface StrategyTypeConfig {
  icon: string;
  label: string;
  description: string;
  color: string;
}

export const STRATEGY_TYPE_CONFIG: Record<StrategyType, StrategyTypeConfig> = {
  // Implementation types
  momentum: {
    icon: '🚀',
    label: 'Momentum',
    description: 'Capitalizes on trend continuation',
    color: '#eb2f96',
  },
  mean_reversion: {
    icon: '↩️',
    label: 'Mean Reversion',
    description: 'Trades on price reversion to mean',
    color: '#13c2c2',
  },
  ensemble: {
    icon: '🤖',
    label: 'Ensemble Model',
    description: 'Combines multiple ML model predictions',
    color: '#a0d911',
  },
  ensemble_model: {  // Template name alias
    icon: '🤖',
    label: 'Ensemble Model',
    description: 'Combines multiple ML model predictions',
    color: '#a0d911',
  },
  stat_arb: {
    icon: '⚖️',
    label: 'Statistical Arbitrage',
    description: 'Exploits statistical mispricing',
    color: '#faad14',
  },
  statistical_arbitrage: {  // Template name alias
    icon: '⚖️',
    label: 'Statistical Arbitrage',
    description: 'Exploits statistical mispricing',
    color: '#faad14',
  },
  // Classification types
  technical: {
    icon: '📊',
    label: 'Technical Analysis',
    description: 'Chart patterns and technical indicators',
    color: '#1890ff',
  },
  technical_analysis: {  // Template name alias
    icon: '📊',
    label: 'Technical Analysis',
    description: 'Chart patterns and technical indicators',
    color: '#1890ff',
  },
  fundamental: {
    icon: '📈',
    label: 'Fundamental Analysis',
    description: 'Company financials and valuations',
    color: '#52c41a',
  },
  fundamental_analysis: {  // Template name alias
    icon: '📈',
    label: 'Fundamental Analysis',
    description: 'Company financials and valuations',
    color: '#52c41a',
  },
  quantitative: {
    icon: '🔢',
    label: 'Quantitative',
    description: 'Mathematical models and ML algorithms',
    color: '#722ed1',
  },
  hybrid: {
    icon: '🎯',
    label: 'Hybrid Strategy',
    description: 'Multi-approach combination',
    color: '#fa8c16',
  },
  hybrid_strategy: {  // Template name alias
    icon: '🎯',
    label: 'Hybrid Strategy',
    description: 'Multi-approach combination',
    color: '#fa8c16',
  },

  optuna_meta: {
    icon: '🧪',
    label: 'Optuna Meta',
    description: 'Optuna research meta-strategy (platform parity)',
    color: '#b37feb',
  },
};

/**
 * Get strategy type configuration
 */
export const getStrategyTypeConfig = (type: StrategyType): StrategyTypeConfig => {
  return STRATEGY_TYPE_CONFIG[type] || STRATEGY_TYPE_CONFIG.momentum;
};

/**
 * Get all strategy types as select options
 */
export const getStrategyTypeOptions = () => {
  return Object.entries(STRATEGY_TYPE_CONFIG).map(([value, config]) => ({
    value,
    label: config.label,
    icon: config.icon,
    description: config.description,
  }));
};
