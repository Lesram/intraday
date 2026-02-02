"""
Production Monitoring Dashboard for Hedge Fund Trading Platform
==============================================================

Real-time portfolio monitoring and visualization with:
- Live portfolio metrics and P&L tracking
- Risk visualizations and alerts
- Drawdown monitoring with historical analysis
- Performance attribution and analytics
- Executive reporting and summaries
- Web-based dashboard interface
- SLO monitoring integration

Created: 2025-09-30
Author: Production Trading System
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import math
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import threading
import time

# Web framework imports with graceful fallback
try:
    from flask import Flask, render_template, jsonify, request
    from flask_socketio import SocketIO, emit
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logging.warning("Flask not available - dashboard will run in headless mode")

# Plotting imports with graceful fallback
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    import base64
    from io import BytesIO
    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False
    logging.warning("Matplotlib not available - charts will be text-based")

# Try importing our internal modules
try:
    from backend.risk.advanced_risk_manager import AdvancedRiskManager, RiskMetrics, RiskLevel
    RISK_MANAGER_AVAILABLE = True
except ImportError:
    RISK_MANAGER_AVAILABLE = False
    logging.warning("Risk Manager not available")

try:
    from backend.optimization.portfolio_optimizer import PortfolioOptimizer, PortfolioAllocation
    OPTIMIZER_AVAILABLE = True
except ImportError:
    OPTIMIZER_AVAILABLE = False
    logging.warning("Portfolio Optimizer not available")

try:
    from backend.monitoring.slo_monitor import SLOMonitor
    SLO_AVAILABLE = True
except ImportError:
    SLO_AVAILABLE = False
    logging.warning("SLO Monitor not available")

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class DashboardStatus(Enum):
    """Dashboard status"""
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class DashboardAlert:
    """Dashboard alert"""
    id: str
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime
    acknowledged: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PortfolioSnapshot:
    """Portfolio snapshot for monitoring"""
    timestamp: datetime
    total_value: float
    pnl_today: float
    pnl_mtd: float
    pnl_ytd: float
    positions_count: int
    leverage: float
    cash_balance: float
    var_1d: float
    max_drawdown: float
    current_drawdown: float
    risk_level: str
    top_positions: List[Dict[str, Any]]
    sector_allocation: Dict[str, float]


@dataclass
class PerformanceMetrics:
    """Performance metrics"""
    returns_1d: float = 0.0
    returns_1w: float = 0.0
    returns_1m: float = 0.0
    returns_3m: float = 0.0
    returns_6m: float = 0.0
    returns_1y: float = 0.0
    volatility_1m: float = 0.0
    volatility_1y: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    var_95_1d: float = 0.0


class ProductionDashboard:
    """
    Production Monitoring Dashboard
    
    Features:
    - Real-time portfolio monitoring and P&L tracking
    - Risk metrics visualization and alerts
    - Performance analytics and attribution
    - Executive summaries and reporting
    - Interactive web interface
    - WebSocket for live updates
    - Alert management system
    - Historical analysis and charting
    """
    
    def __init__(self, 
                 port: int = 5000,
                 update_interval: int = 5,
                 enable_web: bool = True,
                 enable_slo: bool = True):
        """Initialize Production Dashboard"""
        self.port = port
        self.update_interval = update_interval
        self.enable_web = enable_web
        self.status = DashboardStatus.STARTING
        
        # Data storage
        self.portfolio_snapshots: List[PortfolioSnapshot] = []
        self.performance_history: List[PerformanceMetrics] = []
        self.alerts: List[DashboardAlert] = []
        self.current_positions: Dict[str, Any] = {}
        self.pnl_history: List[Tuple[datetime, float]] = []
        
        # Components
        self.risk_manager: Optional[AdvancedRiskManager] = None
        self.portfolio_optimizer: Optional[PortfolioOptimizer] = None
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.update_thread: Optional[threading.Thread] = None
        self.running = False
        
        # Web components
        self.app: Optional[Flask] = None
        self.socketio: Optional[SocketIO] = None
        
        # Initialize components
        self._initialize_components(enable_slo)
        
        if enable_web and FLASK_AVAILABLE:
            self._initialize_web_app()
        
        logger.info(f"Production Dashboard initialized on port {port}")
    
    def _initialize_components(self, enable_slo: bool) -> None:
        """Initialize dashboard components"""
        try:
            # Initialize risk manager
            if RISK_MANAGER_AVAILABLE:
                self.risk_manager = AdvancedRiskManager(enable_slo=enable_slo)
            
            # Initialize portfolio optimizer
            if OPTIMIZER_AVAILABLE:
                self.portfolio_optimizer = PortfolioOptimizer(enable_slo=enable_slo)
            
            # Initialize SLO monitor
            if enable_slo and SLO_AVAILABLE:
                try:
                    self.slo_monitor = SLOMonitor()
                except Exception as e:
                    logger.warning(f"Failed to initialize SLO monitor: {e}")
                    self.slo_monitor = None
            else:
                self.slo_monitor = None
            
        except Exception as e:
            logger.error(f"Error initializing components: {e}")
    
    def _initialize_web_app(self) -> None:
        """Initialize Flask web application"""
        try:
            self.app = Flask(__name__, 
                           template_folder='templates',
                           static_folder='static')
            self.app.config['SECRET_KEY'] = 'production_dashboard_key'
            
            # SECURITY FIX (H-03): Restrict CORS to specific origins instead of wildcard
            # In production, set DASHBOARD_ALLOWED_ORIGINS env var to comma-separated list
            import os
            allowed_origins = os.environ.get('DASHBOARD_ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:5000')
            cors_origins = [origin.strip() for origin in allowed_origins.split(',')]
            
            # Initialize SocketIO for real-time updates with restricted CORS
            self.socketio = SocketIO(self.app, cors_allowed_origins=cors_origins)
            
            # Register routes
            self._register_routes()
            
        except Exception as e:
            logger.error(f"Error initializing web app: {e}")
            self.app = None
            self.socketio = None
    
    def _register_routes(self) -> None:
        """Register web application routes"""
        if not self.app:
            return
        
        @self.app.route('/')
        def dashboard():
            """Main dashboard page"""
            return self._render_dashboard_template()
        
        @self.app.route('/api/portfolio/summary')
        def portfolio_summary():
            """Get portfolio summary"""
            return jsonify(self._get_portfolio_summary())
        
        @self.app.route('/api/performance/metrics')
        def performance_metrics():
            """Get performance metrics"""
            return jsonify(self._get_performance_metrics())
        
        @self.app.route('/api/risk/summary')
        def risk_summary():
            """Get risk summary"""
            return jsonify(self._get_risk_summary())
        
        @self.app.route('/api/alerts')
        def get_alerts():
            """Get active alerts"""
            return jsonify(self._get_active_alerts())
        
        @self.app.route('/api/alerts/<alert_id>/acknowledge', methods=['POST'])
        def acknowledge_alert(alert_id):
            """Acknowledge alert"""
            return jsonify(self._acknowledge_alert(alert_id))
        
        @self.app.route('/api/charts/pnl')
        def pnl_chart():
            """Get P&L chart data"""
            return jsonify(self._get_pnl_chart_data())
        
        @self.app.route('/api/charts/allocation')
        def allocation_chart():
            """Get portfolio allocation chart"""
            return jsonify(self._get_allocation_chart_data())
        
        # WebSocket events
        if self.socketio:
            @self.socketio.on('connect')
            def handle_connect():
                logger.info("Client connected to dashboard")
                emit('status', {'status': self.status.value})
            
            @self.socketio.on('disconnect')
            def handle_disconnect():
                logger.info("Client disconnected from dashboard")
    
    def _render_dashboard_template(self) -> str:
        """Render dashboard template"""
        if FLASK_AVAILABLE:
            try:
                return render_template('dashboard.html')
            except Exception as e:
                logger.error(f"Error rendering template: {e}")
                return self._get_html_fallback()
        else:
            return self._get_html_fallback()
    
    def _get_html_fallback(self) -> str:
        """HTML fallback when template system not available"""
        summary = self._get_portfolio_summary()
        performance = self._get_performance_metrics()
        risk = self._get_risk_summary()
        alerts = self._get_active_alerts()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Production Trading Dashboard</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #1a1a1a; color: #fff; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
                .metric-card {{ background: #2a2a2a; padding: 20px; border-radius: 8px; border-left: 4px solid #00ff88; }}
                .metric-value {{ font-size: 2em; font-weight: bold; margin: 10px 0; }}
                .metric-label {{ color: #888; font-size: 0.9em; }}
                .positive {{ color: #00ff88; }}
                .negative {{ color: #ff4444; }}
                .alerts {{ margin-top: 30px; }}
                .alert {{ background: #444; padding: 15px; margin: 10px 0; border-radius: 5px; }}
                .alert.critical {{ border-left: 4px solid #ff4444; }}
                .alert.warning {{ border-left: 4px solid #ffaa00; }}
                .refresh {{ text-align: center; margin: 20px 0; }}
            </style>
            <script>
                function refreshData() {{
                    location.reload();
                }}
                setInterval(refreshData, 30000); // Refresh every 30 seconds
            </script>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏦 Production Trading Dashboard</h1>
                    <p>Real-time Portfolio Monitoring & Risk Management</p>
                </div>
                
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-label">Portfolio Value</div>
                        <div class="metric-value">${summary.get('total_value', 0):,.0f}</div>
                    </div>
                    
                    <div class="metric-card">
                        <div class="metric-label">P&L Today</div>
                        <div class="metric-value {'positive' if summary.get('pnl_today', 0) >= 0 else 'negative'}">${summary.get('pnl_today', 0):,.0f}</div>
                    </div>
                    
                    <div class="metric-card">
                        <div class="metric-label">Positions</div>
                        <div class="metric-value">{summary.get('positions_count', 0)}</div>
                    </div>
                    
                    <div class="metric-card">
                        <div class="metric-label">Leverage</div>
                        <div class="metric-value">{summary.get('leverage', 0):.2f}x</div>
                    </div>
                    
                    <div class="metric-card">
                        <div class="metric-label">Risk Level</div>
                        <div class="metric-value">{risk.get('risk_level', 'Unknown').upper()}</div>
                    </div>
                    
                    <div class="metric-card">
                        <div class="metric-label">VaR (1D)</div>
                        <div class="metric-value">{risk.get('var_1d', 0):.2%}</div>
                    </div>
                    
                    <div class="metric-card">
                        <div class="metric-label">Sharpe Ratio</div>
                        <div class="metric-value">{performance.get('sharpe_ratio', 0):.2f}</div>
                    </div>
                    
                    <div class="metric-card">
                        <div class="metric-label">Max Drawdown</div>
                        <div class="metric-value negative">{performance.get('max_drawdown', 0):.2%}</div>
                    </div>
                </div>
                
                <div class="alerts">
                    <h2>🚨 Active Alerts ({len(alerts)})</h2>
                    {self._format_alerts_html(alerts)}
                </div>
                
                <div class="refresh">
                    <button onclick="refreshData()" style="padding: 10px 20px; background: #00ff88; border: none; border-radius: 5px; color: black; font-weight: bold; cursor: pointer;">
                        🔄 Refresh Data
                    </button>
                </div>
                
                <div style="text-align: center; margin-top: 30px; color: #888;">
                    <p>Last Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _format_alerts_html(self, alerts: List[Dict]) -> str:
        """Format alerts for HTML display"""
        if not alerts:
            return '<p style="color: #888;">No active alerts</p>'
        
        html = ""
        for alert in alerts[:10]:  # Show only recent alerts
            severity_class = alert.get('severity', 'info')
            html += f'''
            <div class="alert {severity_class}">
                <strong>{alert.get('title', 'Alert')}</strong><br>
                {alert.get('message', 'No message')}
                <div style="font-size: 0.8em; color: #888; margin-top: 10px;">
                    {alert.get('timestamp', 'Unknown time')}
                </div>
            </div>
            '''
        return html
    
    async def update_portfolio_data(self, positions_data: Dict[str, Any], portfolio_value: float, cash_balance: float) -> None:
        """Update portfolio data"""
        try:
            self.current_positions = positions_data
            
            # Update risk manager if available
            if self.risk_manager:
                await self.risk_manager.update_positions(positions_data)
            
            # Create portfolio snapshot
            snapshot = await self._create_portfolio_snapshot(portfolio_value, cash_balance)
            self.portfolio_snapshots.append(snapshot)
            
            # Keep only last 1000 snapshots (roughly 1.5 hours at 5s intervals)
            if len(self.portfolio_snapshots) > 1000:
                self.portfolio_snapshots = self.portfolio_snapshots[-1000:]
            
            # Update P&L history
            self._update_pnl_history(snapshot)
            
            # Check for alerts
            await self._check_alerts(snapshot)
            
            # Emit real-time updates if web enabled
            if self.socketio:
                self.socketio.emit('portfolio_update', {
                    'snapshot': asdict(snapshot),
                    'timestamp': datetime.utcnow().isoformat()
                })
            
        except Exception as e:
            logger.error(f"Error updating portfolio data: {e}")
    
    async def _create_portfolio_snapshot(self, portfolio_value: float, cash_balance: float) -> PortfolioSnapshot:
        """Create portfolio snapshot"""
        try:
            # Get risk metrics
            risk_level = "unknown"
            var_1d = 0.0
            max_drawdown = 0.0
            current_drawdown = 0.0
            leverage = 1.0
            
            if self.risk_manager:
                summary = self.risk_manager.get_risk_summary()
                risk_level = summary.get('risk_metrics', {}).get('risk_level', 'unknown')
                var_1d = summary.get('risk_metrics', {}).get('var_1d', 0.0)
                max_drawdown = summary.get('risk_metrics', {}).get('max_drawdown', 0.0)
                current_drawdown = summary.get('risk_metrics', {}).get('current_drawdown', 0.0)
                leverage = summary.get('portfolio_metrics', {}).get('leverage', 1.0)
            
            # Calculate P&L
            pnl_today = self._calculate_pnl('today', portfolio_value)
            pnl_mtd = self._calculate_pnl('mtd', portfolio_value)
            pnl_ytd = self._calculate_pnl('ytd', portfolio_value)
            
            # Get top positions
            top_positions = self._get_top_positions()
            
            # Get sector allocation
            sector_allocation = self._get_sector_allocation()
            
            return PortfolioSnapshot(
                timestamp=datetime.utcnow(),
                total_value=portfolio_value,
                pnl_today=pnl_today,
                pnl_mtd=pnl_mtd,
                pnl_ytd=pnl_ytd,
                positions_count=len(self.current_positions),
                leverage=leverage,
                cash_balance=cash_balance,
                var_1d=var_1d,
                max_drawdown=max_drawdown,
                current_drawdown=current_drawdown,
                risk_level=risk_level,
                top_positions=top_positions,
                sector_allocation=sector_allocation
            )
            
        except Exception as e:
            logger.error(f"Error creating portfolio snapshot: {e}")
            return PortfolioSnapshot(
                timestamp=datetime.utcnow(),
                total_value=portfolio_value,
                pnl_today=0.0,
                pnl_mtd=0.0,
                pnl_ytd=0.0,
                positions_count=len(self.current_positions),
                leverage=1.0,
                cash_balance=cash_balance,
                var_1d=0.0,
                max_drawdown=0.0,
                current_drawdown=0.0,
                risk_level='unknown',
                top_positions=[],
                sector_allocation={}
            )
    
    def _calculate_pnl(self, period: str, current_value: float) -> float:
        """Calculate P&L for specified period"""
        try:
            if not self.pnl_history:
                return 0.0
            
            now = datetime.utcnow()
            
            if period == 'today':
                start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == 'mtd':
                start_of_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            elif period == 'ytd':
                start_of_day = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                return 0.0
            
            # Find value at start of period
            base_value = None
            for timestamp, value in self.pnl_history:
                if timestamp >= start_of_day:
                    break
                base_value = value
            
            if base_value is None:
                base_value = self.pnl_history[0][1] if self.pnl_history else current_value
            
            return current_value - base_value
            
        except Exception as e:
            logger.error(f"Error calculating P&L for {period}: {e}")
            return 0.0
    
    def _update_pnl_history(self, snapshot: PortfolioSnapshot) -> None:
        """Update P&L history"""
        self.pnl_history.append((snapshot.timestamp, snapshot.total_value))
        
        # Keep only last 30 days
        cutoff_time = datetime.utcnow() - timedelta(days=30)
        self.pnl_history = [(t, v) for t, v in self.pnl_history if t > cutoff_time]
    
    def _get_top_positions(self) -> List[Dict[str, Any]]:
        """Get top positions by market value"""
        try:
            positions = []
            for symbol, data in self.current_positions.items():
                market_value = abs(data.get('market_value', 0))
                positions.append({
                    'symbol': symbol,
                    'market_value': market_value,
                    'quantity': data.get('quantity', 0),
                    'price': data.get('price', 0),
                    'pnl': data.get('pnl', 0),
                    'sector': data.get('sector', 'Unknown')
                })
            
            # Sort by market value and return top 10
            positions.sort(key=lambda x: x['market_value'], reverse=True)
            return positions[:10]
            
        except Exception as e:
            logger.error(f"Error getting top positions: {e}")
            return []
    
    def _get_sector_allocation(self) -> Dict[str, float]:
        """Get sector allocation"""
        try:
            sector_values = {}
            total_value = 0.0
            
            for data in self.current_positions.values():
                market_value = abs(data.get('market_value', 0))
                sector = data.get('sector', 'Unknown')
                
                if sector not in sector_values:
                    sector_values[sector] = 0.0
                
                sector_values[sector] += market_value
                total_value += market_value
            
            # Convert to percentages
            if total_value > 0:
                return {sector: value / total_value for sector, value in sector_values.items()}
            else:
                return {}
                
        except Exception as e:
            logger.error(f"Error calculating sector allocation: {e}")
            return {}
    
    async def _check_alerts(self, snapshot: PortfolioSnapshot) -> None:
        """Check for alerts based on current snapshot"""
        try:
            # Clear old alerts (older than 1 hour)
            cutoff_time = datetime.utcnow() - timedelta(hours=1)
            self.alerts = [alert for alert in self.alerts if alert.timestamp > cutoff_time]
            
            # Check risk level alerts
            if snapshot.risk_level in ['high', 'critical']:
                self._add_alert(
                    AlertSeverity.CRITICAL if snapshot.risk_level == 'critical' else AlertSeverity.WARNING,
                    f"Risk Level {snapshot.risk_level.upper()}",
                    f"Portfolio risk level is {snapshot.risk_level}. Consider reducing exposure.",
                    {'risk_level': snapshot.risk_level}
                )
            
            # Check drawdown alerts
            if abs(snapshot.current_drawdown) > 0.03:  # 3% drawdown
                self._add_alert(
                    AlertSeverity.CRITICAL,
                    "High Drawdown Alert",
                    f"Current drawdown: {snapshot.current_drawdown:.2%}. Review positions immediately.",
                    {'drawdown': snapshot.current_drawdown}
                )
            
            # Check leverage alerts
            if snapshot.leverage > 2.0:
                self._add_alert(
                    AlertSeverity.WARNING,
                    "High Leverage",
                    f"Portfolio leverage is {snapshot.leverage:.2f}x. Monitor risk closely.",
                    {'leverage': snapshot.leverage}
                )
            
            # Check VaR alerts
            if snapshot.var_1d > 0.05:  # 5% VaR
                self._add_alert(
                    AlertSeverity.WARNING,
                    "High VaR",
                    f"1-day VaR is {snapshot.var_1d:.2%}. Consider risk reduction.",
                    {'var_1d': snapshot.var_1d}
                )
            
        except Exception as e:
            logger.error(f"Error checking alerts: {e}")
    
    def _add_alert(self, severity: AlertSeverity, title: str, message: str, metadata: Dict[str, Any]) -> None:
        """Add new alert"""
        # Check if similar alert already exists (avoid spam)
        for existing_alert in self.alerts:
            if existing_alert.title == title and not existing_alert.acknowledged:
                return  # Don't duplicate recent alerts
        
        alert = DashboardAlert(
            id=f"alert_{int(time.time() * 1000)}",
            severity=severity,
            title=title,
            message=message,
            timestamp=datetime.utcnow(),
            metadata=metadata
        )
        
        self.alerts.append(alert)
        
        # Emit real-time alert if web enabled
        if self.socketio:
            self.socketio.emit('new_alert', asdict(alert))
        
        logger.warning(f"Dashboard Alert: [{severity.value.upper()}] {title} - {message}")
    
    def _get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary"""
        if not self.portfolio_snapshots:
            return {'status': 'no_data'}
        
        latest = self.portfolio_snapshots[-1]
        return {
            'total_value': latest.total_value,
            'pnl_today': latest.pnl_today,
            'pnl_mtd': latest.pnl_mtd,
            'pnl_ytd': latest.pnl_ytd,
            'positions_count': latest.positions_count,
            'leverage': latest.leverage,
            'cash_balance': latest.cash_balance,
            'last_updated': latest.timestamp.isoformat(),
            'top_positions': latest.top_positions,
            'sector_allocation': latest.sector_allocation
        }
    
    def _get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics"""
        try:
            if len(self.portfolio_snapshots) < 2:
                return {'status': 'insufficient_data'}
            
            values = [snapshot.total_value for snapshot in self.portfolio_snapshots]
            returns = [(values[i] - values[i-1]) / values[i-1] for i in range(1, len(values))]
            
            if not returns:
                return {'status': 'no_returns'}
            
            # Calculate metrics
            metrics = PerformanceMetrics()
            
            # Recent returns
            if len(returns) >= 1:
                metrics.returns_1d = returns[-1]
            if len(returns) >= 7:
                metrics.returns_1w = (values[-1] - values[-7]) / values[-7]
            if len(returns) >= 30:
                metrics.returns_1m = (values[-1] - values[-30]) / values[-30]
            
            # Volatility (annualized)
            if len(returns) > 1:
                vol = np.std(returns) * math.sqrt(252 * 24 * 12)  # Assuming 5s updates
                metrics.volatility_1m = vol
                metrics.volatility_1y = vol
            
            # Sharpe ratio (annualized)
            if metrics.volatility_1y > 0:
                avg_return = np.mean(returns) * 252 * 24 * 12  # Annualized
                metrics.sharpe_ratio = (avg_return - 0.02) / metrics.volatility_1y  # 2% risk-free rate
            
            # Max drawdown
            peak = values[0]
            max_dd = 0.0
            for value in values:
                if value > peak:
                    peak = value
                dd = (value - peak) / peak
                if dd < max_dd:
                    max_dd = dd
            metrics.max_drawdown = max_dd
            
            return asdict(metrics)
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _get_risk_summary(self) -> Dict[str, Any]:
        """Get risk summary"""
        if self.risk_manager:
            return self.risk_manager.get_risk_summary()
        else:
            latest = self.portfolio_snapshots[-1] if self.portfolio_snapshots else None
            if latest:
                return {
                    'risk_level': latest.risk_level,
                    'var_1d': latest.var_1d,
                    'max_drawdown': latest.max_drawdown,
                    'current_drawdown': latest.current_drawdown,
                    'leverage': latest.leverage
                }
            else:
                return {'status': 'no_data'}
    
    def _get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts"""
        return [asdict(alert) for alert in self.alerts if not alert.acknowledged]
    
    def _acknowledge_alert(self, alert_id: str) -> Dict[str, Any]:
        """Acknowledge alert"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                return {'status': 'acknowledged'}
        return {'status': 'not_found'}
    
    def _get_pnl_chart_data(self) -> Dict[str, Any]:
        """Get P&L chart data"""
        try:
            if not self.pnl_history:
                return {'status': 'no_data'}
            
            # Get last 24 hours
            now = datetime.utcnow()
            start_time = now - timedelta(hours=24)
            
            chart_data = []
            for timestamp, value in self.pnl_history:
                if timestamp >= start_time:
                    chart_data.append({
                        'timestamp': timestamp.isoformat(),
                        'value': value,
                        'pnl': value - self.pnl_history[0][1] if self.pnl_history else 0
                    })
            
            return {
                'data': chart_data,
                'start_time': start_time.isoformat(),
                'end_time': now.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting P&L chart data: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def _get_allocation_chart_data(self) -> Dict[str, Any]:
        """Get allocation chart data"""
        try:
            if not self.portfolio_snapshots:
                return {'status': 'no_data'}
            
            latest = self.portfolio_snapshots[-1]
            
            return {
                'sectors': list(latest.sector_allocation.keys()),
                'allocations': list(latest.sector_allocation.values()),
                'top_positions': latest.top_positions[:5]  # Top 5 for chart
            }
            
        except Exception as e:
            logger.error(f"Error getting allocation chart data: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def start(self) -> None:
        """Start the dashboard"""
        try:
            self.running = True
            self.status = DashboardStatus.RUNNING
            
            # Start update thread
            self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self.update_thread.start()
            
            logger.info("Production Dashboard started successfully")
            
            # Start web server if enabled
            if self.enable_web and self.socketio:
                logger.info(f"Starting web server on port {self.port}")
                self.socketio.run(self.app, host='0.0.0.0', port=self.port, debug=False)
            else:
                logger.info("Dashboard running in headless mode")
                # Keep main thread alive
                while self.running:
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"Error starting dashboard: {e}")
            self.status = DashboardStatus.ERROR
            raise
    
    def stop(self) -> None:
        """Stop the dashboard"""
        self.running = False
        self.status = DashboardStatus.STOPPED
        
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=5)
        
        logger.info("Production Dashboard stopped")
    
    def _update_loop(self) -> None:
        """Background update loop"""
        while self.running:
            try:
                # Perform background updates
                self._cleanup_old_data()
                
                # Sleep for update interval
                time.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"Error in dashboard update loop: {e}")
                time.sleep(self.update_interval)
    
    def _cleanup_old_data(self) -> None:
        """Cleanup old data to prevent memory growth"""
        try:
            # Clean up old snapshots (keep last 24 hours)
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            self.portfolio_snapshots = [s for s in self.portfolio_snapshots if s.timestamp > cutoff_time]
            
            # Clean up old alerts (keep last 24 hours)
            self.alerts = [a for a in self.alerts if a.timestamp > cutoff_time]
            
            # Clean up old P&L history (keep last 30 days)
            pnl_cutoff = datetime.utcnow() - timedelta(days=30)
            self.pnl_history = [(t, v) for t, v in self.pnl_history if t > pnl_cutoff]
            
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
    
    def get_dashboard_status(self) -> Dict[str, Any]:
        """Get dashboard status and statistics"""
        return {
            'status': self.status.value,
            'running': self.running,
            'snapshots_count': len(self.portfolio_snapshots),
            'alerts_count': len([a for a in self.alerts if not a.acknowledged]),
            'pnl_history_count': len(self.pnl_history),
            'components': {
                'risk_manager': self.risk_manager is not None,
                'portfolio_optimizer': self.portfolio_optimizer is not None,
                'web_interface': self.app is not None,
                'websockets': self.socketio is not None
            },
            'last_update': datetime.utcnow().isoformat()
        }


# Example usage and testing
if __name__ == "__main__":
    async def test_dashboard():
        """Test Production Dashboard"""
        print("🖥️ Testing Production Dashboard")
        print("=" * 50)
        
        # Initialize dashboard
        dashboard = ProductionDashboard(port=5001, enable_web=False)  # Headless for testing
        
        # Sample portfolio data
        sample_positions = {
            'AAPL': {
                'quantity': 100,
                'price': 150.0,
                'market_value': 15000,
                'pnl': 500,
                'sector': 'Technology'
            },
            'GOOGL': {
                'quantity': 50,
                'price': 2500.0,
                'market_value': 125000,
                'pnl': -2000,
                'sector': 'Technology'
            },
            'SPY': {
                'quantity': 200,
                'price': 400.0,
                'market_value': 80000,
                'pnl': 1200,
                'sector': 'ETF'
            }
        }
        
        # Update portfolio data
        portfolio_value = sum(pos['market_value'] for pos in sample_positions.values())
        cash_balance = 50000
        
        await dashboard.update_portfolio_data(sample_positions, portfolio_value, cash_balance)
        
        # Get dashboard status
        status = dashboard.get_dashboard_status()
        print("📊 Dashboard Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
        
        # Test API endpoints
        print("\n📈 Portfolio Summary:")
        summary = dashboard._get_portfolio_summary()
        for key, value in summary.items():
            print(f"  {key}: {value}")
        
        print("\n⚠️ Active Alerts:")
        alerts = dashboard._get_active_alerts()
        if alerts:
            for alert in alerts:
                print(f"  [{alert['severity'].upper()}] {alert['title']}: {alert['message']}")
        else:
            print("  No active alerts")
        
        print("\n🎯 Performance Metrics:")
        performance = dashboard._get_performance_metrics()
        for key, value in performance.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.4f}")
            else:
                print(f"  {key}: {value}")
        
        print("\n✅ Production Dashboard test completed successfully!")
        
        return dashboard
    
    # Run test
    dashboard = asyncio.run(test_dashboard())
    
    # Optional: Start web interface
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--web':
        print("\n🌐 Starting web interface on http://localhost:5001")
        dashboard.enable_web = True
        if FLASK_AVAILABLE:
            dashboard._initialize_web_app()
            dashboard.start()
        else:
            print("❌ Flask not available - cannot start web interface")