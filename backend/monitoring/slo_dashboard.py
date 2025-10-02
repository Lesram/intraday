#!/usr/bin/env python3
"""
Real-Time SLO Monitoring Dashboard
Hedge Fund Grade Operations Dashboard
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
from pathlib import Path
import logging

try:
    from flask import Flask, render_template, jsonify, request
    from flask_socketio import SocketIO, emit
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Flask = SocketIO = None

from .slo_metrics import get_slo_collector, SLOMetricsCollector
from .slo_alerts import get_alert_manager, SLOBurnRateAlertManager

class SLODashboard:
    """
    Real-time SLO monitoring dashboard
    Provides hedge fund grade operational visibility
    """
    
    def __init__(self, port: int = 5000):
        """Initialize SLO dashboard"""
        self.port = port
        self.logger = logging.getLogger(__name__)
        
        # Components
        self.slo_collector = get_slo_collector()
        self.alert_manager = get_alert_manager()
        
        # Dashboard state
        self.dashboard_data = {}
        self.last_update = None
        
        # Initialize Flask app if available
        if FLASK_AVAILABLE:
            self.app = Flask(__name__, template_folder='templates')
            self.app.config['SECRET_KEY'] = 'slo_dashboard_secret'
            self.socketio = SocketIO(self.app, cors_allowed_origins="*")
            self._setup_routes()
        else:
            self.app = None
            self.socketio = None

    def _setup_routes(self):
        """Setup Flask routes for dashboard"""
        
        @self.app.route('/')
        def dashboard():
            """Main dashboard page"""
            return render_template('slo_dashboard.html')
        
        @self.app.route('/api/slo/status')
        def slo_status():
            """Get current SLO status"""
            return jsonify(self.get_dashboard_data())
        
        @self.app.route('/api/slo/metrics')
        def slo_metrics():
            """Get Prometheus metrics"""
            try:
                metrics = self.slo_collector.export_prometheus_metrics()
                return metrics.decode('utf-8'), 200, {'Content-Type': 'text/plain; charset=utf-8'}
            except Exception as e:
                return f"Error: {e}", 500
        
        @self.app.route('/api/alerts/status')
        def alert_status():
            """Get alert system status"""
            return jsonify(self.alert_manager.get_alert_status())
        
        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection"""
            self.logger.info('Client connected to SLO dashboard')
            emit('dashboard_data', self.get_dashboard_data())

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data"""
        
        try:
            # Get SLO metrics summary
            slo_summary = self.slo_collector.get_metrics_summary()
            
            # Get alert status
            alert_status = self.alert_manager.get_alert_status()
            
            # Calculate overall system health
            system_health = self._calculate_system_health(slo_summary)
            
            # Recent performance metrics
            performance_metrics = self._get_performance_metrics()
            
            dashboard_data = {
                'timestamp': datetime.now().isoformat(),
                'system_health': system_health,
                'slo_compliance': slo_summary.get('slo_targets', {}),
                'active_violations': slo_summary.get('violations', []),
                'alert_status': alert_status,
                'performance_metrics': performance_metrics,
                'buffer_stats': slo_summary.get('buffer_stats', {}),
                'uptime': self._get_uptime_stats()
            }
            
            self.dashboard_data = dashboard_data
            self.last_update = datetime.now()
            
            return dashboard_data
            
        except Exception as e:
            self.logger.error(f"Error getting dashboard data: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

    def _calculate_system_health(self, slo_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall system health score"""
        
        slo_targets = slo_summary.get('slo_targets', {})
        violations = slo_summary.get('violations', [])
        
        if not slo_targets:
            return {
                'score': 100.0,
                'status': 'unknown',
                'message': 'No SLO data available'
            }
        
        # Calculate weighted health score
        total_score = 0.0
        total_weight = 0.0
        
        # SLO weights (hedge fund priorities)
        slo_weights = {
            'order_submission_latency_p99': 0.35,  # Most critical
            'order_accuracy_daily': 0.30,          # Very critical
            'fill_rate_5min': 0.20,               # Important
            'system_availability_hourly': 0.15     # Important
        }
        
        for slo_name, slo_data in slo_targets.items():
            weight = slo_weights.get(slo_name, 0.1)
            compliance_ratio = slo_data.get('compliance_ratio', 1.0)
            
            # Convert compliance ratio to health score (0-100)
            health_score = compliance_ratio * 100.0
            
            total_score += health_score * weight
            total_weight += weight
        
        overall_score = total_score / total_weight if total_weight > 0 else 100.0
        
        # Determine status
        if overall_score >= 99.0:
            status = 'excellent'
            status_color = '#00C851'  # Green
        elif overall_score >= 95.0:
            status = 'good'
            status_color = '#2E7D32'  # Dark green
        elif overall_score >= 90.0:
            status = 'warning'
            status_color = '#FF8F00'  # Orange
        elif overall_score >= 80.0:
            status = 'degraded'
            status_color = '#FF5722'  # Red-orange
        else:
            status = 'critical'
            status_color = '#F44336'  # Red
        
        # Count critical violations
        critical_violations = len([v for v in violations if v.get('severity') == 'critical'])
        
        return {
            'score': round(overall_score, 1),
            'status': status,
            'status_color': status_color,
            'critical_violations': critical_violations,
            'total_violations': len(violations),
            'message': self._get_health_message(status, critical_violations)
        }

    def _get_health_message(self, status: str, critical_violations: int) -> str:
        """Get system health status message"""
        
        if status == 'excellent':
            return "🎯 All systems operating at peak performance"
        elif status == 'good':
            return "✅ Systems operating within acceptable parameters"
        elif status == 'warning':
            return "⚠️ Minor performance degradation detected"
        elif status == 'degraded':
            if critical_violations > 0:
                return f"🚨 {critical_violations} critical SLO violations active"
            else:
                return "⚡ System performance below targets"
        else:  # critical
            return f"🔥 CRITICAL: {critical_violations} active violations - immediate action required"

    def _get_performance_metrics(self) -> Dict[str, Any]:
        """Get recent performance metrics"""
        
        # This would typically query recent metrics from the collector
        # For now, return sample data structure
        
        now = datetime.now()
        
        return {
            'order_latency': {
                'current_p99_ms': 45.2,
                'target_ms': 100.0,
                'trend': 'stable',
                'last_hour_avg': 42.8
            },
            'order_accuracy': {
                'current_percent': 97.3,
                'target_percent': 95.0,
                'trend': 'improving',
                'daily_success_rate': 98.1
            },
            'fill_rate': {
                'current_percent': 99.1,
                'target_percent': 98.0,
                'trend': 'stable',
                'last_5min_rate': 99.5
            },
            'system_availability': {
                'current_percent': 99.95,
                'target_percent': 99.9,
                'trend': 'stable',
                'uptime_hours': 148.7
            }
        }

    def _get_uptime_stats(self) -> Dict[str, Any]:
        """Get system uptime statistics"""
        
        # This would track actual system uptime
        # For now, return sample data
        
        return {
            'current_uptime_hours': 148.7,
            'last_restart': (datetime.now() - timedelta(hours=148.7)).isoformat(),
            'mttr_minutes': 3.2,  # Mean Time To Recovery
            'mtbf_hours': 720.0   # Mean Time Between Failures
        }

    async def start_realtime_updates(self, update_interval: int = 5):
        """Start real-time dashboard updates via WebSocket"""
        
        if not self.socketio:
            self.logger.warning("SocketIO not available, skipping real-time updates")
            return
        
        async def update_loop():
            while True:
                try:
                    # Get fresh dashboard data
                    data = self.get_dashboard_data()
                    
                    # Emit to all connected clients
                    self.socketio.emit('dashboard_update', data)
                    
                    self.logger.debug(f"Sent dashboard update to clients")
                    
                    # Wait for next update
                    await asyncio.sleep(update_interval)
                    
                except Exception as e:
                    self.logger.error(f"Error in dashboard update loop: {e}")
                    await asyncio.sleep(update_interval)
        
        # Start update loop in background
        asyncio.create_task(update_loop())

    def run_dashboard(self, debug: bool = False, threaded: bool = True):
        """Run the dashboard web server"""
        
        if not FLASK_AVAILABLE:
            self.logger.error("Flask not available. Install with: pip install flask flask-socketio")
            return False
        
        try:
            self.logger.info(f"Starting SLO dashboard on port {self.port}")
            
            # Start real-time updates
            asyncio.create_task(self.start_realtime_updates())
            
            # Run Flask app
            self.socketio.run(
                self.app, 
                host='0.0.0.0', 
                port=self.port, 
                debug=debug,
                allow_unsafe_werkzeug=True
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start dashboard: {e}")
            return False

    def generate_static_report(self, output_file: str = "slo_report.html") -> bool:
        """Generate static HTML report of current SLO status"""
        
        try:
            data = self.get_dashboard_data()
            
            html_content = self._generate_html_report(data)
            
            with open(output_file, 'w') as f:
                f.write(html_content)
            
            self.logger.info(f"Generated SLO report: {output_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to generate report: {e}")
            return False

    def _generate_html_report(self, data: Dict[str, Any]) -> str:
        """Generate HTML report content"""
        
        system_health = data.get('system_health', {})
        slo_compliance = data.get('slo_compliance', {})
        violations = data.get('active_violations', [])
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>SLO Status Report - {data.get('timestamp', 'Unknown')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #1976d2; color: white; padding: 20px; border-radius: 8px; }}
        .metric-card {{ 
            border: 1px solid #ddd; 
            border-radius: 8px; 
            padding: 15px; 
            margin: 10px 0;
            background: white;
        }}
        .health-score {{ font-size: 2em; font-weight: bold; }}
        .status-excellent {{ color: #00C851; }}
        .status-good {{ color: #2E7D32; }}
        .status-warning {{ color: #FF8F00; }}
        .status-degraded {{ color: #FF5722; }}
        .status-critical {{ color: #F44336; }}
        .violation {{ background: #ffebee; border-left: 4px solid #f44336; padding: 10px; margin: 5px 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f5f5f5; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 SLO Status Report</h1>
        <p>Generated: {data.get('timestamp', 'Unknown')}</p>
    </div>
    
    <div class="metric-card">
        <h2>System Health Overview</h2>
        <div class="health-score status-{system_health.get('status', 'unknown')}">
            {system_health.get('score', 0):.1f}%
        </div>
        <p>{system_health.get('message', 'No health data')}</p>
        <p><strong>Status:</strong> {system_health.get('status', 'Unknown').title()}</p>
        <p><strong>Active Violations:</strong> {system_health.get('total_violations', 0)} 
           (Critical: {system_health.get('critical_violations', 0)})</p>
    </div>
    
    <div class="metric-card">
        <h2>SLO Compliance Status</h2>
        <table>
            <tr>
                <th>SLO Target</th>
                <th>Compliance</th>
                <th>Error Budget</th>
                <th>Burn Rate</th>
                <th>Status</th>
            </tr>"""
        
        for slo_name, slo_data in slo_compliance.items():
            compliance = slo_data.get('compliance_ratio', 0) * 100
            error_budget = slo_data.get('error_budget_remaining', 0) * 100
            burn_rate = slo_data.get('burn_rate', 0)
            alert_level = slo_data.get('alert_level', 0)
            
            status_class = 'status-excellent' if alert_level == 0 else ('status-warning' if alert_level == 1 else 'status-critical')
            
            html += f"""
            <tr class="{status_class}">
                <td>{slo_name.replace('_', ' ').title()}</td>
                <td>{compliance:.1f}%</td>
                <td>{error_budget:.1f}%</td>
                <td>{burn_rate:.2f}x</td>
                <td>{'OK' if alert_level == 0 else ('Warning' if alert_level == 1 else 'Critical')}</td>
            </tr>"""
        
        html += """
        </table>
    </div>"""
        
        if violations:
            html += """
    <div class="metric-card">
        <h2>Active SLO Violations</h2>"""
            
            for violation in violations:
                html += f"""
        <div class="violation">
            <strong>{violation.get('slo_name', 'Unknown')}</strong> - {violation.get('severity', 'unknown').upper()}<br>
            Burn Rate: {violation.get('burn_rate', 0):.2f}x<br>
            Actual: {violation.get('actual_value', 0):.3f} | Target: {violation.get('target_value', 0):.3f}
        </div>"""
            
            html += "</div>"
        
        html += """
</body>
</html>"""
        
        return html

# Global dashboard instance
_dashboard = None

def get_dashboard(port: int = 5000) -> SLODashboard:
    """Get global dashboard instance"""
    global _dashboard
    if _dashboard is None:
        _dashboard = SLODashboard(port=port)
    return _dashboard

def start_slo_dashboard(port: int = 5000, debug: bool = False):
    """Start SLO monitoring dashboard"""
    dashboard = get_dashboard(port)
    return dashboard.run_dashboard(debug=debug)