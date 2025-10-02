"""
Memory Usage Monitor and Performance Tracking
Implements automated 24-hour memory usage monitoring and stability validation
for production readiness requirements.
"""

import asyncio
import psutil
import logging
import json
import tracemalloc
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import threading
import time
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    """Memory usage snapshot at a point in time."""
    timestamp: str
    process_memory_mb: float
    system_memory_mb: float
    system_memory_percent: float
    available_memory_mb: float
    swap_usage_mb: float
    swap_percent: float
    python_tracemalloc_mb: float = 0.0  # Python heap memory tracked by tracemalloc
    python_tracemalloc_peak_mb: float = 0.0  # Peak Python memory since start
    top_allocations: List[Dict[str, Any]] = None  # Top memory allocations by line
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MemoryMonitor:
    """
    Comprehensive memory usage monitoring and stability analysis.
    Tracks both process-specific and system-wide memory patterns.
    """
    
    def __init__(self, monitoring_duration_hours: int = 24):
        self.monitoring_duration_hours = monitoring_duration_hours
        self.monitoring_interval_seconds = 300  # 5 minutes
        self.memory_snapshots: List[MemorySnapshot] = []
        
        # Start tracemalloc for Python-level memory tracking
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            logger.info("Started tracemalloc for Python memory tracking")
        else:
            logger.info("tracemalloc already running")
        self.monitoring_active = False
        self.monitoring_thread: Optional[threading.Thread] = None
        self.process = psutil.Process()
        
        # Create monitoring directory
        self.monitoring_dir = Path("monitoring")
        self.monitoring_dir.mkdir(exist_ok=True)
        self.data_file = self.monitoring_dir / "memory_monitoring.json"
        
        # Load existing data if available
        self._load_existing_data()
    
    def _load_existing_data(self):
        """Load existing monitoring data from file."""
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    
                # Convert back to MemorySnapshot objects
                for snapshot_dict in data.get("snapshots", []):
                    snapshot = MemorySnapshot(**snapshot_dict)
                    # Only keep recent snapshots (within monitoring window)
                    snapshot_time = datetime.fromisoformat(snapshot.timestamp.replace('Z', '+00:00'))
                    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.monitoring_duration_hours)
                    
                    if snapshot_time > cutoff_time:
                        self.memory_snapshots.append(snapshot)
                
                logger.info(f"Loaded {len(self.memory_snapshots)} existing memory snapshots")
                
        except Exception as e:
            logger.warning(f"Could not load existing memory data: {e}")
            self.memory_snapshots = []
    
    def _save_data(self):
        """Save monitoring data to file."""
        try:
            data = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "monitoring_duration_hours": self.monitoring_duration_hours,
                "monitoring_interval_seconds": self.monitoring_interval_seconds,
                "snapshots": [snapshot.to_dict() for snapshot in self.memory_snapshots]
            }
            
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Could not save memory monitoring data: {e}")
    
    def start_monitoring(self):
        """Start continuous memory monitoring."""
        if self.monitoring_active:
            logger.warning("Memory monitoring already active")
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitoring_thread.start()
        
        logger.info(f"Started memory monitoring (duration: {self.monitoring_duration_hours}h, interval: {self.monitoring_interval_seconds}s)")
    
    def stop_monitoring(self):
        """Stop continuous memory monitoring."""
        self.monitoring_active = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=10)
        
        self._save_data()
        logger.info("Stopped memory monitoring")
    
    def _monitoring_loop(self):
        """Main monitoring loop (runs in separate thread)."""
        while self.monitoring_active:
            try:
                snapshot = self._take_memory_snapshot()
                self.memory_snapshots.append(snapshot)
                
                # Clean up old snapshots
                self._cleanup_old_snapshots()
                
                # Save data periodically
                self._save_data()
                
                # Wait for next interval
                time.sleep(self.monitoring_interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in memory monitoring loop: {e}")
                time.sleep(60)  # Wait a minute before retrying
    
    def _take_memory_snapshot(self) -> MemorySnapshot:
        """Take a comprehensive memory usage snapshot."""
        try:
            # Process memory (RSS)
            process_memory = self.process.memory_info()
            process_memory_mb = process_memory.rss / 1024 / 1024
            
            # System memory
            system_memory = psutil.virtual_memory()
            system_memory_mb = system_memory.total / 1024 / 1024
            available_memory_mb = system_memory.available / 1024 / 1024
            
            # Swap usage
            swap_info = psutil.swap_memory()
            swap_usage_mb = swap_info.used / 1024 / 1024
            
            # Python tracemalloc data (tracks Python heap allocations)
            python_current_mb = 0.0
            python_peak_mb = 0.0
            top_allocations = []
            
            if tracemalloc.is_tracing():
                current, peak = tracemalloc.get_traced_memory()
                python_current_mb = current / 1024 / 1024
                python_peak_mb = peak / 1024 / 1024
                
                # Get top 10 memory allocations
                snapshot = tracemalloc.take_snapshot()
                top_stats = snapshot.statistics('lineno')[:10]
                
                top_allocations = [
                    {
                        'file': str(stat.traceback),
                        'line': str(stat.traceback.format()[0]) if stat.traceback.format() else 'unknown',
                        'size_mb': round(stat.size / 1024 / 1024, 3),
                        'count': stat.count
                    }
                    for stat in top_stats
                ]
            
            return MemorySnapshot(
                timestamp=datetime.now(timezone.utc).isoformat(),
                process_memory_mb=round(process_memory_mb, 2),
                system_memory_mb=round(system_memory_mb, 2),
                system_memory_percent=round(system_memory.percent, 1),
                available_memory_mb=round(available_memory_mb, 2),
                swap_usage_mb=round(swap_usage_mb, 2),
                swap_percent=round(swap_info.percent, 1),
                python_tracemalloc_mb=round(python_current_mb, 2),
                python_tracemalloc_peak_mb=round(python_peak_mb, 2),
                top_allocations=top_allocations
            )
            
        except Exception as e:
            logger.error(f"Failed to take memory snapshot: {e}")
            # Don't return zeros - raise to fail monitoring
            raise RuntimeError(
                f"Memory monitoring failed: {e}\n"
                "Cannot continue without reliable memory metrics."
            )
    
    def _cleanup_old_snapshots(self):
        """Remove snapshots older than monitoring duration."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.monitoring_duration_hours)
        
        self.memory_snapshots = [
            snapshot for snapshot in self.memory_snapshots
            if datetime.fromisoformat(snapshot.timestamp.replace('Z', '+00:00')) > cutoff_time
        ]
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current memory monitoring status and recent data."""
        current_snapshot = self._take_memory_snapshot()
        
        status = {
            "monitoring_active": self.monitoring_active,
            "monitoring_duration_hours": self.monitoring_duration_hours,
            "total_snapshots": len(self.memory_snapshots),
            "current_snapshot": current_snapshot.to_dict(),
            "data_coverage_hours": 0,
            "oldest_snapshot": None,
            "newest_snapshot": None
        }
        
        if self.memory_snapshots:
            # Calculate data coverage
            oldest = min(self.memory_snapshots, key=lambda s: s.timestamp)
            newest = max(self.memory_snapshots, key=lambda s: s.timestamp)
            
            oldest_time = datetime.fromisoformat(oldest.timestamp.replace('Z', '+00:00'))
            newest_time = datetime.fromisoformat(newest.timestamp.replace('Z', '+00:00'))
            
            coverage_hours = (newest_time - oldest_time).total_seconds() / 3600
            
            status.update({
                "data_coverage_hours": round(coverage_hours, 1),
                "oldest_snapshot": oldest.to_dict(),
                "newest_snapshot": newest.to_dict()
            })
        
        return status
    
    def analyze_stability(self, min_hours: int = 24) -> Dict[str, Any]:
        """
        Analyze memory usage stability over the monitoring period.
        Returns comprehensive stability metrics and pass/fail status.
        """
        analysis = {
            "status": "insufficient_data",
            "data_coverage_hours": 0,
            "min_required_hours": min_hours,
            "stability_metrics": {},
            "memory_trends": {},
            "recommendations": [],
            "pass_criteria": {
                "sufficient_data": False,
                "memory_stable": False,
                "no_memory_leaks": False,
                "system_impact_acceptable": False
            }
        }
        
        try:
            if len(self.memory_snapshots) < 2:
                analysis["recommendations"].append("Start memory monitoring to collect stability data")
                return analysis
            
            # Calculate data coverage
            oldest_time = min(
                datetime.fromisoformat(s.timestamp.replace('Z', '+00:00'))
                for s in self.memory_snapshots
            )
            newest_time = max(
                datetime.fromisoformat(s.timestamp.replace('Z', '+00:00'))
                for s in self.memory_snapshots
            )
            
            coverage_hours = (newest_time - oldest_time).total_seconds() / 3600
            analysis["data_coverage_hours"] = round(coverage_hours, 1)
            
            # Check if we have sufficient data
            if coverage_hours < min_hours:
                analysis["status"] = "insufficient_data"
                analysis["recommendations"].append(
                    f"Need {min_hours - coverage_hours:.1f} more hours of monitoring data"
                )
                return analysis
            
            analysis["pass_criteria"]["sufficient_data"] = True
            
            # Analyze memory stability metrics
            process_memory_values = [s.process_memory_mb for s in self.memory_snapshots]
            system_memory_values = [s.system_memory_percent for s in self.memory_snapshots]
            
            # Process memory analysis
            process_mean = sum(process_memory_values) / len(process_memory_values)
            process_std = (
                sum((x - process_mean) ** 2 for x in process_memory_values) / len(process_memory_values)
            ) ** 0.5
            process_cv = (process_std / process_mean) * 100 if process_mean > 0 else 0
            
            # Memory leak detection (trend analysis)
            memory_growth = self._calculate_trend(process_memory_values)
            
            # System impact analysis
            max_system_memory = max(system_memory_values)
            avg_system_memory = sum(system_memory_values) / len(system_memory_values)
            
            analysis["stability_metrics"] = {
                "process_memory": {
                    "mean_mb": round(process_mean, 2),
                    "std_deviation_mb": round(process_std, 2),
                    "coefficient_of_variation_pct": round(process_cv, 1),
                    "min_mb": round(min(process_memory_values), 2),
                    "max_mb": round(max(process_memory_values), 2)
                },
                "system_memory": {
                    "avg_usage_pct": round(avg_system_memory, 1),
                    "peak_usage_pct": round(max_system_memory, 1),
                    "min_usage_pct": round(min(system_memory_values), 1)
                },
                "memory_growth": {
                    "trend_mb_per_hour": round(memory_growth, 4),
                    "trend_classification": self._classify_memory_trend(memory_growth)
                }
            }
            
            # Stability criteria evaluation
            
            # Memory stability: CV < 20% indicates stable memory usage
            memory_stable = process_cv < 20
            analysis["pass_criteria"]["memory_stable"] = memory_stable
            
            # Memory leak detection: growth < 1MB/hour is acceptable
            no_memory_leaks = abs(memory_growth) < 1.0
            analysis["pass_criteria"]["no_memory_leaks"] = no_memory_leaks
            
            # System impact: peak usage < 80% is acceptable
            system_impact_acceptable = max_system_memory < 80
            analysis["pass_criteria"]["system_impact_acceptable"] = system_impact_acceptable
            
            # Overall status
            all_criteria_met = all(analysis["pass_criteria"].values())
            analysis["status"] = "stable" if all_criteria_met else "unstable"
            
            # Generate recommendations
            recommendations = []
            
            if not memory_stable:
                recommendations.append(
                    f"Memory usage variability is high (CV: {process_cv:.1f}%). "
                    "Consider investigating memory allocation patterns."
                )
            
            if not no_memory_leaks:
                trend_desc = "increase" if memory_growth > 0 else "decrease" 
                recommendations.append(
                    f"Potential memory leak detected: {memory_growth:.2f} MB/hour {trend_desc}. "
                    "Monitor for memory cleanup issues."
                )
            
            if not system_impact_acceptable:
                recommendations.append(
                    f"High system memory usage detected (peak: {max_system_memory:.1f}%). "
                    "Consider optimizing memory allocation or scaling resources."
                )
            
            if all_criteria_met:
                recommendations.append(
                    "Memory usage is stable and within acceptable parameters for production use."
                )
            
            analysis["recommendations"] = recommendations
            
        except Exception as e:
            analysis["error"] = str(e)
            logger.error(f"Memory stability analysis failed: {e}")
        
        return analysis
    
    def _calculate_trend(self, values: List[float]) -> float:
        """Calculate linear trend (slope) of memory usage over time."""
        if len(values) < 2:
            return 0
        
        n = len(values)
        x_values = list(range(n))
        
        # Linear regression to find slope
        x_mean = sum(x_values) / n
        y_mean = sum(values) / n
        
        numerator = sum((x_values[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x_values[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0
        
        slope = numerator / denominator
        
        # Convert to MB per hour
        # slope is in MB per snapshot interval
        intervals_per_hour = 3600 / self.monitoring_interval_seconds
        trend_per_hour = slope * intervals_per_hour
        
        return trend_per_hour
    
    def _classify_memory_trend(self, trend: float) -> str:
        """Classify memory trend based on growth rate."""
        if abs(trend) < 0.1:
            return "stable"
        elif trend > 1.0:
            return "significant_growth"
        elif trend > 0.1:
            return "moderate_growth"
        elif trend < -1.0:
            return "significant_decrease"
        else:
            return "moderate_decrease"
    
    def get_24_hour_validation(self) -> Dict[str, Any]:
        """
        Validate 24-hour memory stability for production readiness.
        Returns pass/fail status with detailed metrics.
        """
        
        # Ensure monitoring is active
        if not self.monitoring_active:
            self.start_monitoring()
        
        # Get current status
        status = self.get_current_status()
        
        # Perform stability analysis
        stability = self.analyze_stability(min_hours=24)
        
        validation = {
            "validation_timestamp": datetime.now(timezone.utc).isoformat(),
            "requirement": "Memory usage stable over 24-hour period",
            "status": "unknown",
            "monitoring_status": status,
            "stability_analysis": stability,
            "production_ready": False,
            "next_steps": []
        }
        
        try:
            # Determine validation status
            if stability["status"] == "insufficient_data":
                validation["status"] = "monitoring_in_progress"
                validation["next_steps"].append(
                    f"Continue monitoring for {24 - status.get('data_coverage_hours', 0):.1f} more hours"
                )
            elif stability["status"] == "stable":
                validation["status"] = "passed"
                validation["production_ready"] = True
                validation["next_steps"].append("Memory stability validated for production use")
            else:
                validation["status"] = "failed"
                validation["next_steps"].extend(stability.get("recommendations", []))
            
            # Add monitoring guidance
            if status["data_coverage_hours"] < 24:
                validation["next_steps"].append(
                    "Memory monitoring will continue automatically in the background"
                )
            
        except Exception as e:
            validation["status"] = "error"
            validation["error"] = str(e)
            validation["next_steps"].append("Investigate memory monitoring system error")
        
        return validation


# Global memory monitor instance
memory_monitor = MemoryMonitor()


# Convenience functions
def start_memory_monitoring():
    """Start 24-hour memory monitoring."""
    memory_monitor.start_monitoring()


def stop_memory_monitoring():
    """Stop memory monitoring and save data."""
    memory_monitor.stop_monitoring()


def get_memory_status() -> Dict[str, Any]:
    """Get current memory monitoring status."""
    return memory_monitor.get_current_status()


def validate_24_hour_memory_stability() -> Dict[str, Any]:
    """Validate memory stability for production readiness."""
    return memory_monitor.get_24_hour_validation()


def analyze_memory_stability() -> Dict[str, Any]:
    """Analyze memory usage stability."""
    return memory_monitor.analyze_stability()


# Auto-start monitoring when module is imported
if not memory_monitor.monitoring_active:
    memory_monitor.start_monitoring()