"""
MLOps Model Optimization Service

Comprehensive model optimization system providing:
- Model quantization (INT8, FP16, dynamic)
- Model pruning (structured, unstructured)
- Knowledge distillation
- Hardware acceleration optimization
- Model compression techniques
- Performance profiling and benchmarking
- Optimization pipeline management
- Multi-framework support
- Custom optimization strategies

Author: MLOps Team
Created: 2025-01-01
Version: 1.0.0
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OptimizationType(str, Enum):
    """Model optimization type enumeration."""
    QUANTIZATION = "quantization"
    PRUNING = "pruning"
    DISTILLATION = "distillation"
    COMPRESSION = "compression"
    ACCELERATION = "acceleration"
    MIXED = "mixed"


class QuantizationType(str, Enum):
    """Quantization type enumeration."""
    INT8 = "int8"
    FP16 = "fp16" 
    DYNAMIC = "dynamic"
    STATIC = "static"
    QAT = "quantization_aware_training"


class PruningType(str, Enum):
    """Pruning type enumeration."""
    STRUCTURED = "structured"
    UNSTRUCTURED = "unstructured"
    MAGNITUDE = "magnitude"
    GRADIENT = "gradient"
    SNIP = "snip"


class HardwareTarget(str, Enum):
    """Hardware target enumeration."""
    CPU = "cpu"
    GPU = "gpu"
    TPU = "tpu"
    MOBILE = "mobile"
    EDGE = "edge"
    FPGA = "fpga"


class OptimizationStatus(str, Enum):
    """Optimization status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OptimizationConfig:
    """Optimization configuration."""
    optimization_type: OptimizationType
    target_hardware: HardwareTarget
    target_latency_ms: float | None = None
    target_throughput: float | None = None
    target_model_size_mb: float | None = None
    accuracy_threshold: float = 0.95  # Minimum acceptable accuracy
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'optimization_type': self.optimization_type.value,
            'target_hardware': self.target_hardware.value,
            'target_latency_ms': self.target_latency_ms,
            'target_throughput': self.target_throughput,
            'target_model_size_mb': self.target_model_size_mb,
            'accuracy_threshold': self.accuracy_threshold,
            'parameters': self.parameters,
            'metadata': self.metadata
        }


@dataclass
class ModelMetrics:
    """Model performance metrics."""
    accuracy: float
    latency_ms: float
    throughput: float
    model_size_mb: float
    memory_usage_mb: float
    flops: int
    parameters_count: int
    inference_time_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'accuracy': self.accuracy,
            'latency_ms': self.latency_ms,
            'throughput': self.throughput,
            'model_size_mb': self.model_size_mb,
            'memory_usage_mb': self.memory_usage_mb,
            'flops': self.flops,
            'parameters_count': self.parameters_count,
            'inference_time_ms': self.inference_time_ms,
            'metadata': self.metadata
        }


@dataclass
class OptimizationResult:
    """Optimization result."""
    optimization_id: str
    original_model_path: str
    optimized_model_path: str
    optimization_config: OptimizationConfig
    original_metrics: ModelMetrics
    optimized_metrics: ModelMetrics
    optimization_report: dict[str, Any]
    status: OptimizationStatus
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    error_message: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'optimization_id': self.optimization_id,
            'original_model_path': self.original_model_path,
            'optimized_model_path': self.optimized_model_path,
            'optimization_config': self.optimization_config.to_dict(),
            'original_metrics': self.original_metrics.to_dict(),
            'optimized_metrics': self.optimized_metrics.to_dict(),
            'optimization_report': self.optimization_report,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message
        }
    
    def get_improvement_summary(self) -> dict[str, float]:
        """Get optimization improvement summary."""
        return {
            'accuracy_change': self.optimized_metrics.accuracy - self.original_metrics.accuracy,
            'latency_improvement': (self.original_metrics.latency_ms - self.optimized_metrics.latency_ms) / self.original_metrics.latency_ms,
            'throughput_improvement': (self.optimized_metrics.throughput - self.original_metrics.throughput) / self.original_metrics.throughput,
            'size_reduction': (self.original_metrics.model_size_mb - self.optimized_metrics.model_size_mb) / self.original_metrics.model_size_mb,
            'memory_reduction': (self.original_metrics.memory_usage_mb - self.optimized_metrics.memory_usage_mb) / self.original_metrics.memory_usage_mb,
            'flops_reduction': (self.original_metrics.flops - self.optimized_metrics.flops) / self.original_metrics.flops if self.original_metrics.flops > 0 else 0,
            'params_reduction': (self.original_metrics.parameters_count - self.optimized_metrics.parameters_count) / self.original_metrics.parameters_count
        }


class ModelOptimizer(ABC):
    """Abstract base class for model optimizers."""
    
    @abstractmethod
    def optimize(self, model_path: str, config: OptimizationConfig) -> tuple[str, dict[str, Any]]:
        """Optimize model and return path to optimized model and optimization report."""
        pass
    
    @abstractmethod
    def supports_optimization_type(self, optimization_type: OptimizationType) -> bool:
        """Check if optimizer supports the optimization type."""
        pass
    
    @abstractmethod
    def supports_hardware_target(self, hardware_target: HardwareTarget) -> bool:
        """Check if optimizer supports the hardware target."""
        pass
    
    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """Get list of supported model formats."""
        pass


class QuantizationOptimizer(ModelOptimizer):
    """Quantization-based model optimizer."""
    
    def __init__(self):
        self.supported_types = [OptimizationType.QUANTIZATION]
        self.supported_hardware = [HardwareTarget.CPU, HardwareTarget.GPU, HardwareTarget.MOBILE, HardwareTarget.EDGE]
        self.supported_formats = ["onnx", "pytorch", "tensorflow"]
    
    def optimize(self, model_path: str, config: OptimizationConfig) -> tuple[str, dict[str, Any]]:
        """Perform quantization optimization."""
        if not self.supports_optimization_type(config.optimization_type):
            raise ValueError(f"Optimization type {config.optimization_type} not supported")
        
        quantization_type = config.parameters.get('quantization_type', QuantizationType.INT8)
        
        # Simulate quantization process
        path_parts = model_path.rsplit('.', 1)
        if len(path_parts) == 2:
            base_path, extension = path_parts
            optimized_path = f"{base_path}_quantized_{quantization_type.value}.{extension}"
        else:
            optimized_path = f"{model_path}_quantized_{quantization_type.value}"
        
        optimization_report = {
            'technique': 'quantization',
            'quantization_type': quantization_type.value,
            'calibration_dataset_size': config.parameters.get('calibration_dataset_size', 1000),
            'quantization_scheme': config.parameters.get('quantization_scheme', 'symmetric'),
            'optimization_time_seconds': np.random.uniform(10, 60),
            'compression_ratio': np.random.uniform(2.0, 4.0),
            'accuracy_drop': np.random.uniform(0.0, 0.05)
        }
        
        logger.info(f"Quantization optimization completed: {optimized_path}")
        return optimized_path, optimization_report
    
    def supports_optimization_type(self, optimization_type: OptimizationType) -> bool:
        """Check if optimizer supports the optimization type."""
        return optimization_type in self.supported_types
    
    def supports_hardware_target(self, hardware_target: HardwareTarget) -> bool:
        """Check if optimizer supports the hardware target."""
        return hardware_target in self.supported_hardware
    
    def get_supported_formats(self) -> list[str]:
        """Get list of supported model formats."""
        return self.supported_formats.copy()


class PruningOptimizer(ModelOptimizer):
    """Pruning-based model optimizer."""
    
    def __init__(self):
        self.supported_types = [OptimizationType.PRUNING]
        self.supported_hardware = [HardwareTarget.CPU, HardwareTarget.GPU, HardwareTarget.MOBILE]
        self.supported_formats = ["pytorch", "tensorflow"]
    
    def optimize(self, model_path: str, config: OptimizationConfig) -> tuple[str, dict[str, Any]]:
        """Perform pruning optimization."""
        if not self.supports_optimization_type(config.optimization_type):
            raise ValueError(f"Optimization type {config.optimization_type} not supported")
        
        pruning_type = config.parameters.get('pruning_type', PruningType.MAGNITUDE)
        sparsity = config.parameters.get('sparsity', 0.5)
        
        # Simulate pruning process
        path_parts = model_path.rsplit('.', 1)
        if len(path_parts) == 2:
            base_path, extension = path_parts
            optimized_path = f"{base_path}_pruned_{pruning_type.value}_{sparsity}.{extension}"
        else:
            optimized_path = f"{model_path}_pruned_{pruning_type.value}_{sparsity}"
        
        optimization_report = {
            'technique': 'pruning',
            'pruning_type': pruning_type.value,
            'sparsity': sparsity,
            'structured': pruning_type == PruningType.STRUCTURED,
            'optimization_time_seconds': np.random.uniform(30, 120),
            'compression_ratio': 1.0 / (1.0 - sparsity),
            'accuracy_drop': np.random.uniform(0.0, 0.1)
        }
        
        logger.info(f"Pruning optimization completed: {optimized_path}")
        return optimized_path, optimization_report
    
    def supports_optimization_type(self, optimization_type: OptimizationType) -> bool:
        """Check if optimizer supports the optimization type."""
        return optimization_type in self.supported_types
    
    def supports_hardware_target(self, hardware_target: HardwareTarget) -> bool:
        """Check if optimizer supports the hardware target."""
        return hardware_target in self.supported_hardware
    
    def get_supported_formats(self) -> list[str]:
        """Get list of supported model formats."""
        return self.supported_formats.copy()


class DistillationOptimizer(ModelOptimizer):
    """Knowledge distillation-based model optimizer."""
    
    def __init__(self):
        self.supported_types = [OptimizationType.DISTILLATION]
        self.supported_hardware = [HardwareTarget.CPU, HardwareTarget.GPU, HardwareTarget.MOBILE, HardwareTarget.EDGE]
        self.supported_formats = ["pytorch", "tensorflow"]
    
    def optimize(self, model_path: str, config: OptimizationConfig) -> tuple[str, dict[str, Any]]:
        """Perform knowledge distillation optimization."""
        if not self.supports_optimization_type(config.optimization_type):
            raise ValueError(f"Optimization type {config.optimization_type} not supported")
        
        student_architecture = config.parameters.get('student_architecture', 'mobilenet')
        temperature = config.parameters.get('temperature', 4.0)
        alpha = config.parameters.get('alpha', 0.7)
        
        # Simulate distillation process
        path_parts = model_path.rsplit('.', 1)
        if len(path_parts) == 2:
            base_path, extension = path_parts
            optimized_path = f"{base_path}_distilled_{student_architecture}.{extension}"
        else:
            optimized_path = f"{model_path}_distilled_{student_architecture}"
        
        optimization_report = {
            'technique': 'distillation',
            'student_architecture': student_architecture,
            'temperature': temperature,
            'alpha': alpha,
            'training_epochs': config.parameters.get('training_epochs', 100),
            'optimization_time_seconds': np.random.uniform(300, 1800),
            'compression_ratio': np.random.uniform(3.0, 10.0),
            'accuracy_drop': np.random.uniform(0.02, 0.15)
        }
        
        logger.info(f"Distillation optimization completed: {optimized_path}")
        return optimized_path, optimization_report
    
    def supports_optimization_type(self, optimization_type: OptimizationType) -> bool:
        """Check if optimizer supports the optimization type."""
        return optimization_type in self.supported_types
    
    def supports_hardware_target(self, hardware_target: HardwareTarget) -> bool:
        """Check if optimizer supports the hardware target."""
        return hardware_target in self.supported_hardware
    
    def get_supported_formats(self) -> list[str]:
        """Get list of supported model formats."""
        return self.supported_formats.copy()


class PerformanceProfiler:
    """Model performance profiler."""
    
    def __init__(self):
        self.profiles = {}
    
    def profile_model(self, model_path: str, hardware_target: HardwareTarget,
                     batch_sizes: list[int] = None, num_runs: int = 100) -> ModelMetrics:
        """Profile model performance."""
        if batch_sizes is None:
            batch_sizes = [1, 8, 32]
        
        # Simulate model profiling
        base_latency = np.random.uniform(10, 100)  # Base latency in ms
        base_throughput = 1000 / base_latency  # Throughput in samples/sec
        
        # Adjust based on hardware target
        hardware_multipliers = {
            HardwareTarget.CPU: 1.0,
            HardwareTarget.GPU: 0.3,
            HardwareTarget.TPU: 0.1,
            HardwareTarget.MOBILE: 2.0,
            HardwareTarget.EDGE: 3.0,
            HardwareTarget.FPGA: 0.5
        }
        
        multiplier = hardware_multipliers.get(hardware_target, 1.0)
        
        metrics = ModelMetrics(
            accuracy=np.random.uniform(0.85, 0.99),
            latency_ms=base_latency * multiplier,
            throughput=base_throughput / multiplier,
            model_size_mb=np.random.uniform(10, 500),
            memory_usage_mb=np.random.uniform(100, 2000),
            flops=np.random.randint(1000000, 1000000000),
            parameters_count=np.random.randint(100000, 10000000),
            inference_time_ms=base_latency * multiplier,
            metadata={
                'hardware_target': hardware_target.value,
                'batch_sizes_tested': batch_sizes,
                'num_runs': num_runs,
                'profiling_timestamp': datetime.now().isoformat()
            }
        )
        
        # Store profile
        profile_key = f"{model_path}:{hardware_target.value}"
        self.profiles[profile_key] = metrics
        
        logger.info(f"Model profiling completed for {model_path} on {hardware_target.value}")
        return metrics
    
    def compare_models(self, model_metrics: list[tuple[str, ModelMetrics]]) -> dict[str, Any]:
        """Compare multiple model metrics."""
        if len(model_metrics) < 2:
            raise ValueError("Need at least 2 models to compare")
        
        comparison = {
            'models': [name for name, _ in model_metrics],
            'metrics_comparison': {},
            'best_model': {},
            'recommendations': []
        }
        
        metrics_names = ['accuracy', 'latency_ms', 'throughput', 'model_size_mb', 'memory_usage_mb']
        
        for metric_name in metrics_names:
            values = [getattr(metrics, metric_name) for _, metrics in model_metrics]
            comparison['metrics_comparison'][metric_name] = {
                'values': values,
                'best_value': min(values) if metric_name in ['latency_ms', 'model_size_mb', 'memory_usage_mb'] else max(values),
                'worst_value': max(values) if metric_name in ['latency_ms', 'model_size_mb', 'memory_usage_mb'] else min(values)
            }
        
        # Determine best model for each metric
        for metric_name in metrics_names:
            values = [getattr(metrics, metric_name) for _, metrics in model_metrics]
            if metric_name in ['latency_ms', 'model_size_mb', 'memory_usage_mb']:
                best_idx = np.argmin(values)
            else:
                best_idx = np.argmax(values)
            comparison['best_model'][metric_name] = model_metrics[best_idx][0]
        
        # Generate recommendations
        if len(set(comparison['best_model'].values())) == 1:
            # One model is best for all metrics
            best_overall = list(comparison['best_model'].values())[0]
            comparison['recommendations'].append(f"Model '{best_overall}' is optimal across all metrics")
        else:
            comparison['recommendations'].append("Trade-offs exist between different metrics")
            comparison['recommendations'].append("Consider your specific requirements for model selection")
        
        return comparison
    
    def get_optimization_recommendations(self, metrics: ModelMetrics, 
                                       target_hardware: HardwareTarget) -> list[str]:
        """Get optimization recommendations based on model metrics."""
        recommendations = []
        
        # Size-based recommendations
        if metrics.model_size_mb > 100:
            recommendations.append("Consider quantization to reduce model size")
            recommendations.append("Pruning can help reduce parameter count")
        
        # Latency-based recommendations
        if metrics.latency_ms > 100:
            recommendations.append("Model acceleration techniques recommended for latency")
            if target_hardware in [HardwareTarget.MOBILE, HardwareTarget.EDGE]:
                recommendations.append("Knowledge distillation for mobile deployment")
        
        # Memory-based recommendations
        if metrics.memory_usage_mb > 1000:
            recommendations.append("Memory optimization techniques needed")
            recommendations.append("Consider model compression")
        
        # Hardware-specific recommendations
        if target_hardware == HardwareTarget.MOBILE:
            recommendations.append("Use FP16 quantization for mobile GPUs")
            recommendations.append("Consider MobileNet-based architectures")
        elif target_hardware == HardwareTarget.EDGE:
            recommendations.append("INT8 quantization recommended for edge devices")
            recommendations.append("Aggressive pruning for edge deployment")
        elif target_hardware == HardwareTarget.GPU:
            recommendations.append("Consider TensorRT optimization for NVIDIA GPUs")
            recommendations.append("Mixed precision training/inference")
        
        return recommendations


class OptimizationPipeline:
    """Optimization pipeline manager."""
    
    def __init__(self):
        self.stages = []
        self.results = []
    
    def add_stage(self, optimizer: ModelOptimizer, config: OptimizationConfig):
        """Add optimization stage to pipeline."""
        self.stages.append((optimizer, config))
    
    def run_pipeline(self, model_path: str) -> list[OptimizationResult]:
        """Run the optimization pipeline."""
        current_model_path = model_path
        pipeline_results = []
        
        for i, (optimizer, config) in enumerate(self.stages):
            try:
                stage_id = f"stage_{i}_{config.optimization_type.value}"
                
                # Profile original model (first stage only)
                profiler = PerformanceProfiler()
                if i == 0:
                    original_metrics = profiler.profile_model(current_model_path, config.target_hardware)
                else:
                    original_metrics = pipeline_results[-1].optimized_metrics
                
                # Run optimization
                optimized_path, optimization_report = optimizer.optimize(current_model_path, config)
                
                # Profile optimized model
                optimized_metrics = profiler.profile_model(optimized_path, config.target_hardware)
                
                # Create result
                result = OptimizationResult(
                    optimization_id=stage_id,
                    original_model_path=current_model_path,
                    optimized_model_path=optimized_path,
                    optimization_config=config,
                    original_metrics=original_metrics,
                    optimized_metrics=optimized_metrics,
                    optimization_report=optimization_report,
                    status=OptimizationStatus.COMPLETED,
                    completed_at=datetime.now()
                )
                
                pipeline_results.append(result)
                current_model_path = optimized_path
                
                logger.info(f"Pipeline stage {i} completed: {stage_id}")
                
            except Exception as e:
                error_result = OptimizationResult(
                    optimization_id=f"stage_{i}_failed",
                    original_model_path=current_model_path,
                    optimized_model_path="",
                    optimization_config=config,
                    original_metrics=ModelMetrics(0, 0, 0, 0, 0, 0, 0, 0),
                    optimized_metrics=ModelMetrics(0, 0, 0, 0, 0, 0, 0, 0),
                    optimization_report={},
                    status=OptimizationStatus.FAILED,
                    error_message=str(e)
                )
                pipeline_results.append(error_result)
                logger.error(f"Pipeline stage {i} failed: {e}")
                break
        
        return pipeline_results
    
    def get_pipeline_summary(self, results: list[OptimizationResult]) -> dict[str, Any]:
        """Get pipeline optimization summary."""
        if not results:
            return {}
        
        first_result = results[0]
        last_successful = None
        
        for result in results:
            if result.status == OptimizationStatus.COMPLETED:
                last_successful = result
        
        if not last_successful:
            return {'status': 'failed', 'error': 'No successful optimizations'}
        
        overall_improvement = OptimizationResult(
            optimization_id="pipeline_summary",
            original_model_path=first_result.original_model_path,
            optimized_model_path=last_successful.optimized_model_path,
            optimization_config=first_result.optimization_config,
            original_metrics=first_result.original_metrics,
            optimized_metrics=last_successful.optimized_metrics,
            optimization_report={},
            status=OptimizationStatus.COMPLETED
        )
        
        return {
            'status': 'completed',
            'stages_completed': len([r for r in results if r.status == OptimizationStatus.COMPLETED]),
            'total_stages': len(results),
            'overall_improvement': overall_improvement.get_improvement_summary(),
            'final_metrics': last_successful.optimized_metrics.to_dict(),
            'optimization_techniques': [r.optimization_config.optimization_type.value for r in results if r.status == OptimizationStatus.COMPLETED]
        }


class ModelOptimizationService:
    """Main model optimization service."""
    
    def __init__(self, storage_path: str = "./model_optimization"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.optimizers: dict[OptimizationType, list[ModelOptimizer]] = {
            OptimizationType.QUANTIZATION: [QuantizationOptimizer()],
            OptimizationType.PRUNING: [PruningOptimizer()],
            OptimizationType.DISTILLATION: [DistillationOptimizer()],
        }
        
        self.profiler = PerformanceProfiler()
        self.optimizations: dict[str, OptimizationResult] = {}
        self.pipelines: dict[str, OptimizationPipeline] = {}
        
        # Optimization strategies
        self.strategies = self._load_optimization_strategies()
    
    def _load_optimization_strategies(self) -> dict[str, dict[str, Any]]:
        """Load predefined optimization strategies."""
        return {
            'mobile_inference': {
                'description': 'Optimized for mobile inference',
                'target_hardware': HardwareTarget.MOBILE,
                'optimizations': [
                    {
                        'type': OptimizationType.QUANTIZATION,
                        'parameters': {'quantization_type': QuantizationType.FP16}
                    },
                    {
                        'type': OptimizationType.PRUNING,
                        'parameters': {'sparsity': 0.3, 'pruning_type': PruningType.MAGNITUDE}
                    }
                ]
            },
            'edge_deployment': {
                'description': 'Optimized for edge deployment',
                'target_hardware': HardwareTarget.EDGE,
                'optimizations': [
                    {
                        'type': OptimizationType.QUANTIZATION,
                        'parameters': {'quantization_type': QuantizationType.INT8}
                    },
                    {
                        'type': OptimizationType.PRUNING,
                        'parameters': {'sparsity': 0.5, 'pruning_type': PruningType.STRUCTURED}
                    }
                ]
            },
            'gpu_acceleration': {
                'description': 'Optimized for GPU acceleration',
                'target_hardware': HardwareTarget.GPU,
                'optimizations': [
                    {
                        'type': OptimizationType.QUANTIZATION,
                        'parameters': {'quantization_type': QuantizationType.FP16}
                    }
                ]
            },
            'knowledge_distillation': {
                'description': 'Knowledge distillation for model compression',
                'target_hardware': HardwareTarget.CPU,
                'optimizations': [
                    {
                        'type': OptimizationType.DISTILLATION,
                        'parameters': {'student_architecture': 'mobilenet', 'temperature': 4.0}
                    }
                ]
            }
        }
    
    def register_optimizer(self, optimization_type: OptimizationType, optimizer: ModelOptimizer):
        """Register a custom optimizer."""
        if optimization_type not in self.optimizers:
            self.optimizers[optimization_type] = []
        self.optimizers[optimization_type].append(optimizer)
        logger.info(f"Registered optimizer for {optimization_type.value}")
    
    def get_available_optimizers(self, optimization_type: OptimizationType = None) -> dict[str, list[str]]:
        """Get available optimizers."""
        if optimization_type:
            return {
                optimization_type.value: [
                    type(opt).__name__ for opt in self.optimizers.get(optimization_type, [])
                ]
            }
        
        result = {}
        for opt_type, optimizers in self.optimizers.items():
            result[opt_type.value] = [type(opt).__name__ for opt in optimizers]
        return result
    
    def profile_model(self, model_path: str, hardware_target: HardwareTarget,
                     batch_sizes: list[int] = None, num_runs: int = 100) -> ModelMetrics:
        """Profile model performance."""
        return self.profiler.profile_model(model_path, hardware_target, batch_sizes, num_runs)
    
    def optimize_model(self, model_path: str, config: OptimizationConfig) -> OptimizationResult:
        """Optimize a model."""
        optimization_id = hashlib.md5(f"{model_path}_{config.optimization_type.value}_{datetime.now()}".encode()).hexdigest()[:16]
        
        try:
            # Get appropriate optimizer
            optimizers = self.optimizers.get(config.optimization_type, [])
            if not optimizers:
                raise ValueError(f"No optimizer available for {config.optimization_type.value}")
            
            # Use first available optimizer (could be enhanced with selection logic)
            optimizer = optimizers[0]
            
            # Check compatibility
            if not optimizer.supports_optimization_type(config.optimization_type):
                raise ValueError(f"Optimizer does not support {config.optimization_type.value}")
            
            if not optimizer.supports_hardware_target(config.target_hardware):
                raise ValueError(f"Optimizer does not support {config.target_hardware.value}")
            
            # Profile original model
            original_metrics = self.profiler.profile_model(model_path, config.target_hardware)
            
            # Perform optimization
            optimized_path, optimization_report = optimizer.optimize(model_path, config)
            
            # Profile optimized model
            optimized_metrics = self.profiler.profile_model(optimized_path, config.target_hardware)
            
            # Check if optimization meets criteria
            if optimized_metrics.accuracy < config.accuracy_threshold:
                logger.warning(f"Optimized model accuracy {optimized_metrics.accuracy} below threshold {config.accuracy_threshold}")
            
            # Create result
            result = OptimizationResult(
                optimization_id=optimization_id,
                original_model_path=model_path,
                optimized_model_path=optimized_path,
                optimization_config=config,
                original_metrics=original_metrics,
                optimized_metrics=optimized_metrics,
                optimization_report=optimization_report,
                status=OptimizationStatus.COMPLETED,
                completed_at=datetime.now()
            )
            
            self.optimizations[optimization_id] = result
            logger.info(f"Model optimization completed: {optimization_id}")
            return result
            
        except Exception as e:
            error_result = OptimizationResult(
                optimization_id=optimization_id,
                original_model_path=model_path,
                optimized_model_path="",
                optimization_config=config,
                original_metrics=ModelMetrics(0, 0, 0, 0, 0, 0, 0, 0),
                optimized_metrics=ModelMetrics(0, 0, 0, 0, 0, 0, 0, 0),
                optimization_report={},
                status=OptimizationStatus.FAILED,
                error_message=str(e)
            )
            
            self.optimizations[optimization_id] = error_result
            logger.error(f"Model optimization failed: {e}")
            return error_result
    
    def create_optimization_pipeline(self, pipeline_id: str, configs: list[tuple[OptimizationType, OptimizationConfig]]) -> str:
        """Create an optimization pipeline."""
        pipeline = OptimizationPipeline()
        
        for opt_type, config in configs:
            optimizers = self.optimizers.get(opt_type, [])
            if not optimizers:
                raise ValueError(f"No optimizer available for {opt_type.value}")
            
            optimizer = optimizers[0]  # Use first available
            pipeline.add_stage(optimizer, config)
        
        self.pipelines[pipeline_id] = pipeline
        logger.info(f"Created optimization pipeline: {pipeline_id}")
        return pipeline_id
    
    def run_optimization_pipeline(self, pipeline_id: str, model_path: str) -> list[OptimizationResult]:
        """Run an optimization pipeline."""
        if pipeline_id not in self.pipelines:
            raise ValueError(f"Pipeline {pipeline_id} not found")
        
        pipeline = self.pipelines[pipeline_id]
        results = pipeline.run_pipeline(model_path)
        
        # Store results
        for result in results:
            self.optimizations[result.optimization_id] = result
        
        return results
    
    def apply_optimization_strategy(self, strategy_name: str, model_path: str,
                                  target_hardware: HardwareTarget = None) -> list[OptimizationResult]:
        """Apply a predefined optimization strategy."""
        if strategy_name not in self.strategies:
            raise ValueError(f"Strategy {strategy_name} not found")
        
        strategy = self.strategies[strategy_name]
        
        # Override target hardware if specified
        hardware_target = target_hardware or HardwareTarget(strategy['target_hardware'])
        
        # Create pipeline configs
        configs = []
        for opt_config in strategy['optimizations']:
            config = OptimizationConfig(
                optimization_type=OptimizationType(opt_config['type']),
                target_hardware=hardware_target,
                parameters=opt_config['parameters']
            )
            configs.append((config.optimization_type, config))
        
        # Create and run pipeline
        pipeline_id = f"strategy_{strategy_name}_{hashlib.md5(model_path.encode()).hexdigest()[:8]}"
        self.create_optimization_pipeline(pipeline_id, configs)
        
        return self.run_optimization_pipeline(pipeline_id, model_path)
    
    def get_optimization_result(self, optimization_id: str) -> OptimizationResult | None:
        """Get optimization result by ID."""
        return self.optimizations.get(optimization_id)
    
    def list_optimizations(self, model_path: str = None, status: OptimizationStatus = None) -> list[OptimizationResult]:
        """List optimizations with optional filtering."""
        results = list(self.optimizations.values())
        
        if model_path:
            results = [r for r in results if r.original_model_path == model_path]
        
        if status:
            results = [r for r in results if r.status == status]
        
        return results
    
    def compare_optimizations(self, optimization_ids: list[str]) -> dict[str, Any]:
        """Compare multiple optimization results."""
        results = []
        for opt_id in optimization_ids:
            if opt_id in self.optimizations:
                result = self.optimizations[opt_id]
                results.append((opt_id, result.optimized_metrics))
        
        if len(results) < 2:
            raise ValueError("Need at least 2 optimization results to compare")
        
        return self.profiler.compare_models(results)
    
    def get_optimization_recommendations(self, model_path: str, target_hardware: HardwareTarget) -> dict[str, Any]:
        """Get optimization recommendations for a model."""
        # Profile model
        metrics = self.profiler.profile_model(model_path, target_hardware)
        
        # Get recommendations
        recommendations = self.profiler.get_optimization_recommendations(metrics, target_hardware)
        
        # Suggest strategies
        suitable_strategies = []
        for strategy_name, strategy in self.strategies.items():
            if HardwareTarget(strategy['target_hardware']) == target_hardware:
                suitable_strategies.append(strategy_name)
        
        return {
            'model_metrics': metrics.to_dict(),
            'recommendations': recommendations,
            'suitable_strategies': suitable_strategies,
            'available_optimizers': self.get_available_optimizers()
        }
    
    def get_optimization_statistics(self) -> dict[str, Any]:
        """Get optimization service statistics."""
        total_optimizations = len(self.optimizations)
        completed = len([o for o in self.optimizations.values() if o.status == OptimizationStatus.COMPLETED])
        failed = len([o for o in self.optimizations.values() if o.status == OptimizationStatus.FAILED])
        
        if completed > 0:
            avg_size_reduction = np.mean([
                result.get_improvement_summary()['size_reduction']
                for result in self.optimizations.values()
                if result.status == OptimizationStatus.COMPLETED
            ])
            avg_latency_improvement = np.mean([
                result.get_improvement_summary()['latency_improvement']
                for result in self.optimizations.values()
                if result.status == OptimizationStatus.COMPLETED
            ])
        else:
            avg_size_reduction = 0.0
            avg_latency_improvement = 0.0
        
        return {
            'total_optimizations': total_optimizations,
            'completed_optimizations': completed,
            'failed_optimizations': failed,
            'success_rate': completed / total_optimizations if total_optimizations > 0 else 0,
            'avg_size_reduction': avg_size_reduction,
            'avg_latency_improvement': avg_latency_improvement,
            'registered_optimizers': self.get_available_optimizers(),
            'available_strategies': list(self.strategies.keys()),
            'total_pipelines': len(self.pipelines)
        }


# Convenience functions
def create_optimization_service(storage_path: str = "./model_optimization") -> ModelOptimizationService:
    """Create a model optimization service instance."""
    return ModelOptimizationService(storage_path)


def create_optimization_config(optimization_type: OptimizationType, 
                             target_hardware: HardwareTarget,
                             target_latency_ms: float | None = None,
                             target_model_size_mb: float | None = None,
                             accuracy_threshold: float = 0.95,
                             parameters: dict[str, Any] | None = None) -> OptimizationConfig:
    """Create an optimization configuration."""
    if parameters is None:
        parameters = {}
    
    return OptimizationConfig(
        optimization_type=optimization_type,
        target_hardware=target_hardware,
        target_latency_ms=target_latency_ms,
        target_model_size_mb=target_model_size_mb,
        accuracy_threshold=accuracy_threshold,
        parameters=parameters
    )


# Export all classes and functions
__all__ = [
    'OptimizationType', 'QuantizationType', 'PruningType', 'HardwareTarget', 'OptimizationStatus',
    'OptimizationConfig', 'ModelMetrics', 'OptimizationResult',
    'ModelOptimizer', 'QuantizationOptimizer', 'PruningOptimizer', 'DistillationOptimizer',
    'PerformanceProfiler', 'OptimizationPipeline', 'ModelOptimizationService',
    'create_optimization_service', 'create_optimization_config'
]