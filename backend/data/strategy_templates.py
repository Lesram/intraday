"""
Strategy parameter templates for all strategy types.
Provides default parameters, validation schemas, and descriptions for the strategy builder wizard.
"""

from typing import Any

from pydantic import BaseModel, Field, field_serializer


class ParameterTemplate(BaseModel):
    """Template for a single strategy parameter"""
    name: str
    type: str  # "number", "boolean", "string", "select", "multiselect"
    default: Any
    min: float | None = None
    max: float | None = None
    options: list[str] | None = None
    description: str
    required: bool = True
    label: str | None = None  # Display label (optional, defaults to name)

    @field_serializer('options')
    def serialize_options(self, options: list[str] | None) -> list[dict[str, str]] | None:
        """Convert string list to {value, label} objects for frontend"""
        if options is None:
            return None
        return [{"value": opt, "label": opt.replace("_", " ").title()} for opt in options]


class StrategyTemplate(BaseModel):
    """Complete template for a strategy type"""
    type: str
    name: str
    description: str
    category: str
    icon: str
    parameters: list[ParameterTemplate]
    risk_defaults: dict[str, Any] = Field(alias="riskDefaults")

    model_config = {"populate_by_name": True}


# Define all 8 strategy templates
STRATEGY_TEMPLATES: dict[str, StrategyTemplate] = {
    "technical_analysis": StrategyTemplate(
        type="technical_analysis",
        name="Technical Analysis",
        description="Trading based on technical indicators like moving averages, RSI, MACD",
        category="Technical",
        icon="📊",
        parameters=[
            ParameterTemplate(
                name="short_ma_period",
                type="number",
                default=20,
                min=5,
                max=100,
                description="Short-term moving average period (days)",
                required=True
            ),
            ParameterTemplate(
                name="long_ma_period",
                type="number",
                default=50,
                min=20,
                max=200,
                description="Long-term moving average period (days)",
                required=True
            ),
            ParameterTemplate(
                name="rsi_period",
                type="number",
                default=14,
                min=7,
                max=30,
                description="RSI calculation period",
                required=True
            ),
            ParameterTemplate(
                name="rsi_overbought",
                type="number",
                default=70,
                min=60,
                max=90,
                description="RSI overbought threshold",
                required=True
            ),
            ParameterTemplate(
                name="rsi_oversold",
                type="number",
                default=30,
                min=10,
                max=40,
                description="RSI oversold threshold",
                required=True
            ),
            ParameterTemplate(
                name="macd_fast",
                type="number",
                default=12,
                min=8,
                max=20,
                description="MACD fast period",
                required=False
            ),
            ParameterTemplate(
                name="macd_slow",
                type="number",
                default=26,
                min=20,
                max=35,
                description="MACD slow period",
                required=False
            ),
            ParameterTemplate(
                name="macd_signal",
                type="number",
                default=9,
                min=5,
                max=15,
                description="MACD signal period",
                required=False
            ),
        ],
        riskDefaults={
            "maxPositionSize": 10000.0,
            "dailyLossLimit": 1000.0,
            "maxDrawdown": 0.15,
            "stopLossPercent": 0.02,
            "takeProfitPercent": 0.05
        }
    ),
    "fundamental_analysis": StrategyTemplate(
        type="fundamental_analysis",
        name="Fundamental Analysis",
        description="Trading based on company fundamentals like P/E ratio, earnings, revenue",
        category="Fundamental",
        icon="📈",
        parameters=[
            ParameterTemplate(
                name="max_pe_ratio",
                type="number",
                default=25.0,
                min=5.0,
                max=50.0,
                description="Maximum P/E ratio for buy signal",
                required=True
            ),
            ParameterTemplate(
                name="min_revenue_growth",
                type="number",
                default=0.10,
                min=0.0,
                max=1.0,
                description="Minimum revenue growth rate (10% = 0.10)",
                required=True
            ),
            ParameterTemplate(
                name="min_earnings_growth",
                type="number",
                default=0.15,
                min=0.0,
                max=1.0,
                description="Minimum earnings growth rate (15% = 0.15)",
                required=True
            ),
            ParameterTemplate(
                name="max_debt_to_equity",
                type="number",
                default=0.50,
                min=0.0,
                max=2.0,
                description="Maximum debt-to-equity ratio",
                required=True
            ),
            ParameterTemplate(
                name="min_roe",
                type="number",
                default=0.15,
                min=0.0,
                max=1.0,
                description="Minimum return on equity (ROE)",
                required=False
            ),
        ],
        riskDefaults={
            "maxPositionSize": 15000.0,
            "dailyLossLimit": 1500.0,
            "maxDrawdown": 0.20,
            "stopLossPercent": 0.05,
            "takeProfitPercent": 0.10
        }
    ),
    "quantitative": StrategyTemplate(
        type="quantitative",
        name="Quantitative",
        description="Mathematical and statistical models for systematic trading",
        category="Quantitative",
        icon="🔢",
        parameters=[
            ParameterTemplate(
                name="model_type",
                type="select",
                default="lstm",
                options=["lstm", "arima", "garch", "kalman_filter"],
                description="Statistical model type",
                required=True
            ),
            ParameterTemplate(
                name="lookback_period",
                type="number",
                default=60,
                min=20,
                max=252,
                description="Historical data lookback period (days)",
                required=True
            ),
            ParameterTemplate(
                name="confidence_threshold",
                type="number",
                default=0.80,
                min=0.50,
                max=0.99,
                description="Minimum prediction confidence (80% = 0.80)",
                required=True
            ),
            ParameterTemplate(
                name="rebalance_frequency",
                type="select",
                default="weekly",
                options=["daily", "weekly", "monthly"],
                description="Portfolio rebalancing frequency",
                required=True
            ),
        ],
        riskDefaults={
            "maxPositionSize": 12000.0,
            "dailyLossLimit": 1200.0,
            "maxDrawdown": 0.18,
            "stopLossPercent": 0.03,
            "takeProfitPercent": 0.06
        }
    ),
    "hybrid_strategy": StrategyTemplate(
        type="hybrid_strategy",
        name="Hybrid Strategy",
        description="Combines technical, fundamental, and ML signals for robust trading",
        category="Hybrid",
        icon="🎯",
        parameters=[
            ParameterTemplate(
                name="technical_weight",
                type="number",
                default=0.40,
                min=0.0,
                max=1.0,
                description="Weight of technical signals (40% = 0.40)",
                required=True
            ),
            ParameterTemplate(
                name="fundamental_weight",
                type="number",
                default=0.30,
                min=0.0,
                max=1.0,
                description="Weight of fundamental signals (30% = 0.30)",
                required=True
            ),
            ParameterTemplate(
                name="ml_weight",
                type="number",
                default=0.30,
                min=0.0,
                max=1.0,
                description="Weight of ML predictions (30% = 0.30)",
                required=True
            ),
            ParameterTemplate(
                name="min_consensus",
                type="number",
                default=0.65,
                min=0.50,
                max=1.0,
                description="Minimum consensus across signals to trade",
                required=True
            ),
        ],
        riskDefaults={
            "maxPositionSize": 13000.0,
            "dailyLossLimit": 1300.0,
            "maxDrawdown": 0.16,
            "stopLossPercent": 0.025,
            "takeProfitPercent": 0.07
        }
    ),
    "momentum": StrategyTemplate(
        type="momentum",
        name="Momentum",
        description="Trend continuation strategy - ride strong trends",
        category="Technical",
        icon="🚀",
        parameters=[
            ParameterTemplate(
                name="lookback_days",
                type="number",
                default=20,
                min=5,
                max=60,
                description="Period to measure momentum (days)",
                required=True
            ),
            ParameterTemplate(
                name="min_momentum_threshold",
                type="number",
                default=0.05,
                min=0.01,
                max=0.20,
                description="Minimum momentum to enter (5% = 0.05)",
                required=True
            ),
            ParameterTemplate(
                name="trailing_stop_percent",
                type="number",
                default=0.03,
                min=0.01,
                max=0.10,
                description="Trailing stop loss percentage",
                required=True
            ),
            ParameterTemplate(
                name="volume_confirmation",
                type="boolean",
                default=True,
                description="Require volume confirmation for signals",
                required=False
            ),
        ],
        riskDefaults={
            "maxPositionSize": 11000.0,
            "dailyLossLimit": 1100.0,
            "maxDrawdown": 0.20,
            "stopLossPercent": 0.03,
            "takeProfitPercent": 0.08
        }
    ),
    "mean_reversion": StrategyTemplate(
        type="mean_reversion",
        name="Mean Reversion",
        description="Profit from price returning to average levels",
        category="Technical",
        icon="↩️",
        parameters=[
            ParameterTemplate(
                name="mean_period",
                type="number",
                default=20,
                min=10,
                max=100,
                description="Period to calculate mean (days)",
                required=True
            ),
            ParameterTemplate(
                name="std_dev_threshold",
                type="number",
                default=2.0,
                min=1.0,
                max=3.0,
                description="Standard deviations from mean to trigger",
                required=True
            ),
            ParameterTemplate(
                name="mean_reversion_speed",
                type="select",
                default="medium",
                options=["fast", "medium", "slow"],
                description="Expected reversion speed",
                required=True
            ),
            ParameterTemplate(
                name="exit_at_mean",
                type="boolean",
                default=True,
                description="Exit position when price returns to mean",
                required=False
            ),
        ],
        riskDefaults={
            "maxPositionSize": 10000.0,
            "dailyLossLimit": 1000.0,
            "maxDrawdown": 0.15,
            "stopLossPercent": 0.04,
            "takeProfitPercent": 0.06
        }
    ),
    "ensemble_model": StrategyTemplate(
        type="ensemble_model",
        name="Ensemble Model",
        description="Multiple ML models voting on trade decisions",
        category="Machine Learning",
        icon="🤖",
        parameters=[
            ParameterTemplate(
                name="models",
                type="select",
                default="all",
                options=["all", "random_forest_gradient_boost", "lstm_arima", "custom"],
                description="Which models to include in ensemble",
                required=True
            ),
            ParameterTemplate(
                name="voting_method",
                type="select",
                default="weighted",
                options=["majority", "weighted", "unanimous"],
                description="How models vote on decisions",
                required=True
            ),
            ParameterTemplate(
                name="min_model_agreement",
                type="number",
                default=0.75,
                min=0.50,
                max=1.0,
                description="Minimum % of models that must agree",
                required=True
            ),
            ParameterTemplate(
                name="retrain_frequency_days",
                type="number",
                default=7,
                min=1,
                max=30,
                description="Days between model retraining",
                required=True
            ),
        ],
        riskDefaults={
            "maxPositionSize": 14000.0,
            "dailyLossLimit": 1400.0,
            "maxDrawdown": 0.17,
            "stopLossPercent": 0.025,
            "takeProfitPercent": 0.075
        }
    ),
    "statistical_arbitrage": StrategyTemplate(
        type="statistical_arbitrage",
        name="Statistical Arbitrage",
        description="Exploit statistical mispricings between correlated assets",
        category="Quantitative",
        icon="⚖️",
        parameters=[
            ParameterTemplate(
                name="correlation_threshold",
                type="number",
                default=0.80,
                min=0.50,
                max=0.99,
                description="Minimum correlation between pairs",
                required=True
            ),
            ParameterTemplate(
                name="zscore_entry",
                type="number",
                default=2.0,
                min=1.0,
                max=3.0,
                description="Z-score threshold to enter trade",
                required=True
            ),
            ParameterTemplate(
                name="zscore_exit",
                type="number",
                default=0.5,
                min=0.0,
                max=1.5,
                description="Z-score threshold to exit trade",
                required=True
            ),
            ParameterTemplate(
                name="pair_selection",
                type="select",
                default="automatic",
                options=["automatic", "manual", "sector_based"],
                description="How to select trading pairs",
                required=True
            ),
        ],
        riskDefaults={
            "maxPositionSize": 20000.0,
            "dailyLossLimit": 2000.0,
            "maxDrawdown": 0.12,
            "stopLossPercent": 0.02,
            "takeProfitPercent": 0.04
        }
    ),
}


def get_template(strategy_type: str) -> StrategyTemplate | None:
    """Get template for a specific strategy type"""
    return STRATEGY_TEMPLATES.get(strategy_type)


def get_all_templates() -> list[StrategyTemplate]:
    """Get all strategy templates"""
    return list(STRATEGY_TEMPLATES.values())


def get_default_parameters(strategy_type: str) -> dict[str, Any]:
    """Get default parameter values for a strategy type"""
    template = get_template(strategy_type)
    if not template:
        return {}

    return {param.name: param.default for param in template.parameters}


def get_default_risk_limits(strategy_type: str) -> dict[str, Any]:
    """Get default risk limits for a strategy type"""
    template = get_template(strategy_type)
    if not template:
        return {}

    return template.risk_defaults
