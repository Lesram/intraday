"""
Module 64: MLOps Pipeline Orchestration Service

This module provides comprehensive pipeline orchestration functionality for managing
ML workflows, stages, dependencies, execution coordination, and monitoring.
Supports complex multi-stage pipelines with conditional execution and error handling.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Union, Any, Tuple, Callable, Set
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PipelineStatus(Enum):
    """Pipeline execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    SKIPPED = "skipped"


class StageStatus(Enum):
    """Pipeline stage status."""
    WAITING = "waiting"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class ExecutionMode(Enum):
    """Pipeline execution mode."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    DAG = "dag"


class PipelineType(Enum):
    """Pipeline type classification."""
    TRAINING = "training"
    INFERENCE = "inference"
    DATA_PROCESSING = "data_processing"
    MODEL_VALIDATION = "model_validation"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    CUSTOM = "custom"


@dataclass
class PipelineConfig:
    """Pipeline configuration."""
    name: str
    description: str = ""
    pipeline_type: PipelineType = PipelineType.CUSTOM
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    max_parallel_stages: int = 4
    timeout_seconds: int = 3600
    retry_attempts: int = 3
    retry_delay: float = 30.0
    environment: Dict[str, Any] = field(default_factory=dict)
    notifications: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class StageConfig:
    """Pipeline stage configuration."""
    name: str
    stage_type: str
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 1800
    retry_attempts: int = 2
    retry_delay: float = 10.0
    skip_on_failure: bool = False
    condition: Optional[str] = None
    resources: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)


@dataclass
class StageResult:
    """Stage execution result."""
    stage_id: str
    status: StageStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: float = 0.0
    output: Any = None
    error: Optional[str] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    """Pipeline execution result."""
    pipeline_id: str
    run_id: str
    status: PipelineStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: float = 0.0
    stage_results: Dict[str, StageResult] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)


class PipelineStage(ABC):
    """Abstract base class for pipeline stages."""
    
    def __init__(self, config: StageConfig):
        self.config = config
        self.stage_id = f"{config.name}_{int(time.time())}"
        self.status = StageStatus.WAITING
        self.result: Optional[StageResult] = None
    
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Any:
        """Execute the stage."""
        pass
    
    def validate_config(self) -> bool:
        """Validate stage configuration."""
        return bool(self.config.name and self.config.stage_type)
    
    def check_dependencies(self, completed_stages: Set[str]) -> bool:
        """Check if stage dependencies are satisfied."""
        return all(dep in completed_stages for dep in self.config.dependencies)
    
    def evaluate_condition(self, context: Dict[str, Any]) -> bool:
        """Evaluate stage execution condition."""
        if not self.config.condition:
            return True
        
        try:
            # Simple condition evaluation
            return eval(self.config.condition, {"__builtins__": {}}, context)
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {e}")
            return True


class DataProcessingStage(PipelineStage):
    """Data processing pipeline stage."""
    
    async def execute(self, context: Dict[str, Any]) -> Any:
        """Execute data processing."""
        logger.info(f"Executing data processing stage: {self.config.name}")
        
        # Simulate data processing
        await asyncio.sleep(0.1)
        
        # Get input data from context or parameters
        input_data = context.get('data', self.config.parameters.get('input_data', []))
        processing_type = self.config.parameters.get('processing_type', 'transform')
        
        if processing_type == 'filter':
            # Filter data based on condition
            condition = self.config.parameters.get('filter_condition', lambda x: True)
            result = [item for item in input_data if condition(item)]
        elif processing_type == 'transform':
            # Transform data
            transform_func = self.config.parameters.get('transform_func', lambda x: x)
            result = [transform_func(item) for item in input_data]
        elif processing_type == 'aggregate':
            # Aggregate data
            result = {
                'count': len(input_data),
                'sum': sum(input_data) if all(isinstance(x, (int, float)) for x in input_data) else 0,
                'data_sample': input_data[:5] if input_data else []
            }
        else:
            result = input_data
        
        return result


class ModelTrainingStage(PipelineStage):
    """Model training pipeline stage."""
    
    async def execute(self, context: Dict[str, Any]) -> Any:
        """Execute model training."""
        logger.info(f"Executing model training stage: {self.config.name}")
        
        # Simulate training time
        training_time = self.config.parameters.get('training_time', 0.2)
        await asyncio.sleep(training_time)
        
        # Get training parameters
        model_type = self.config.parameters.get('model_type', 'linear_regression')
        hyperparameters = self.config.parameters.get('hyperparameters', {})
        
        # Simulate training result
        result = {
            'model_id': f"model_{uuid.uuid4().hex[:8]}",
            'model_type': model_type,
            'hyperparameters': hyperparameters,
            'training_metrics': {
                'accuracy': 0.85 + 0.1 * hash(model_type) % 10 / 100,
                'loss': 0.15 + 0.05 * hash(str(hyperparameters)) % 10 / 100,
                'training_time': training_time
            },
            'model_path': f"/models/{model_type}_{int(time.time())}.pkl"
        }
        
        return result


class ModelValidationStage(PipelineStage):
    """Model validation pipeline stage."""
    
    async def execute(self, context: Dict[str, Any]) -> Any:
        """Execute model validation."""
        logger.info(f"Executing model validation stage: {self.config.name}")
        
        await asyncio.sleep(0.1)
        
        # Get model from context
        model_info = context.get('model', {})
        validation_data = context.get('validation_data', [])
        
        # Simulate validation
        result = {
            'validation_metrics': {
                'accuracy': model_info.get('training_metrics', {}).get('accuracy', 0.8) * 0.95,
                'precision': 0.82,
                'recall': 0.79,
                'f1_score': 0.80
            },
            'validation_passed': True,
            'model_id': model_info.get('model_id', 'unknown'),
            'validation_data_size': len(validation_data)
        }
        
        return result


class DeploymentStage(PipelineStage):
    """Model deployment pipeline stage."""
    
    async def execute(self, context: Dict[str, Any]) -> Any:
        """Execute model deployment."""
        logger.info(f"Executing deployment stage: {self.config.name}")
        
        await asyncio.sleep(0.15)
        
        model_info = context.get('model', {})
        deployment_config = self.config.parameters.get('deployment_config', {})
        
        result = {
            'deployment_id': f"deploy_{uuid.uuid4().hex[:8]}",
            'endpoint_url': f"https://api.example.com/models/{model_info.get('model_id', 'unknown')}",
            'deployment_status': 'active',
            'deployment_config': deployment_config,
            'health_check_url': f"https://api.example.com/health/{model_info.get('model_id', 'unknown')}"
        }
        
        return result


class PipelineExecutor:
    """Pipeline execution engine."""
    
    def __init__(self):
        self.pipelines: Dict[str, 'Pipeline'] = {}
        self.execution_history: List[PipelineResult] = []
        self.active_runs: Dict[str, PipelineResult] = {}
    
    async def execute_pipeline(self, pipeline: 'Pipeline', 
                             context: Optional[Dict[str, Any]] = None) -> PipelineResult:
        """Execute a pipeline."""
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()
        
        if context is None:
            context = {}
        
        # Create pipeline result
        result = PipelineResult(
            pipeline_id=pipeline.pipeline_id,
            run_id=run_id,
            status=PipelineStatus.RUNNING,
            start_time=start_time
        )
        
        self.active_runs[run_id] = result
        
        try:
            logger.info(f"Starting pipeline execution: {pipeline.config.name}")
            
            if pipeline.config.execution_mode == ExecutionMode.SEQUENTIAL:
                await self._execute_sequential(pipeline, context, result)
            elif pipeline.config.execution_mode == ExecutionMode.PARALLEL:
                await self._execute_parallel(pipeline, context, result)
            elif pipeline.config.execution_mode == ExecutionMode.DAG:
                await self._execute_dag(pipeline, context, result)
            else:
                await self._execute_sequential(pipeline, context, result)
            
            result.status = PipelineStatus.SUCCEEDED
            logger.info(f"Pipeline execution completed: {pipeline.config.name}")
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            result.status = PipelineStatus.FAILED
            result.error = str(e)
        
        # Finalize result
        result.end_time = datetime.now()
        result.duration = (result.end_time - result.start_time).total_seconds()
        
        # Move to history
        self.execution_history.append(result)
        if run_id in self.active_runs:
            del self.active_runs[run_id]
        
        return result
    
    async def _execute_sequential(self, pipeline: 'Pipeline', 
                                 context: Dict[str, Any], 
                                 result: PipelineResult):
        """Execute pipeline stages sequentially."""
        for stage in pipeline.stages:
            if result.status == PipelineStatus.CANCELLED:
                break
            
            stage_result = await self._execute_stage(stage, context, result)
            result.stage_results[stage.stage_id] = stage_result
            
            if stage_result.status == StageStatus.FAILED and not stage.config.skip_on_failure:
                raise Exception(f"Stage {stage.config.name} failed: {stage_result.error}")
            
            # Update context with stage output
            if stage_result.output is not None:
                context[stage.config.name] = stage_result.output
    
    async def _execute_parallel(self, pipeline: 'Pipeline', 
                               context: Dict[str, Any], 
                               result: PipelineResult):
        """Execute pipeline stages in parallel."""
        # Group stages by dependency level
        stage_groups = self._group_stages_by_dependencies(pipeline.stages)
        
        for group in stage_groups:
            if result.status == PipelineStatus.CANCELLED:
                break
            
            # Execute stages in group concurrently
            tasks = []
            for stage in group:
                task = self._execute_stage(stage, context, result)
                tasks.append((stage, task))
            
            # Wait for all stages in group to complete
            for stage, task in tasks:
                stage_result = await task
                result.stage_results[stage.stage_id] = stage_result
                
                if stage_result.status == StageStatus.FAILED and not stage.config.skip_on_failure:
                    # Cancel remaining tasks
                    for _, other_task in tasks:
                        if not other_task.done():
                            other_task.cancel()
                    raise Exception(f"Stage {stage.config.name} failed: {stage_result.error}")
                
                # Update context with stage output
                if stage_result.output is not None:
                    context[stage.config.name] = stage_result.output
    
    async def _execute_dag(self, pipeline: 'Pipeline', 
                          context: Dict[str, Any], 
                          result: PipelineResult):
        """Execute pipeline as DAG (Directed Acyclic Graph)."""
        completed_stages: Set[str] = set()
        running_stages: Dict[str, asyncio.Task] = {}
        pending_stages = list(pipeline.stages)
        
        while pending_stages or running_stages:
            if result.status == PipelineStatus.CANCELLED:
                break
            
            # Start ready stages
            ready_stages = []
            remaining_stages = []
            
            for stage in pending_stages:
                if stage.check_dependencies(completed_stages):
                    ready_stages.append(stage)
                else:
                    remaining_stages.append(stage)
            
            pending_stages = remaining_stages
            
            # Start ready stages (respect max parallel limit)
            max_parallel = pipeline.config.max_parallel_stages
            while ready_stages and len(running_stages) < max_parallel:
                stage = ready_stages.pop(0)
                task = asyncio.create_task(self._execute_stage(stage, context, result))
                running_stages[stage.stage_id] = task
            
            # Wait for at least one stage to complete
            if running_stages:
                done, pending = await asyncio.wait(
                    running_stages.values(),
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Process completed stages
                for task in done:
                    # Find the stage for this task
                    stage_id = None
                    for sid, stask in running_stages.items():
                        if stask == task:
                            stage_id = sid
                            break
                    
                    if stage_id:
                        stage = next(s for s in pipeline.stages if s.stage_id == stage_id)
                        stage_result = await task
                        result.stage_results[stage_id] = stage_result
                        
                        if stage_result.status == StageStatus.SUCCEEDED:
                            completed_stages.add(stage.config.name)
                            # Update context with stage output
                            if stage_result.output is not None:
                                context[stage.config.name] = stage_result.output
                        elif stage_result.status == StageStatus.FAILED and not stage.config.skip_on_failure:
                            # Cancel all running stages
                            for other_task in running_stages.values():
                                if not other_task.done():
                                    other_task.cancel()
                            raise Exception(f"Stage {stage.config.name} failed: {stage_result.error}")
                        
                        del running_stages[stage_id]
    
    async def _execute_stage(self, stage: PipelineStage, 
                           context: Dict[str, Any], 
                           pipeline_result: PipelineResult) -> StageResult:
        """Execute a single stage."""
        start_time = datetime.now()
        stage_result = StageResult(
            stage_id=stage.stage_id,
            status=StageStatus.RUNNING,
            start_time=start_time
        )
        
        try:
            # Check condition
            if not stage.evaluate_condition(context):
                stage_result.status = StageStatus.SKIPPED
                logger.info(f"Stage {stage.config.name} skipped due to condition")
                return stage_result
            
            # Execute stage with retry logic
            for attempt in range(stage.config.retry_attempts + 1):
                try:
                    logger.info(f"Executing stage {stage.config.name} (attempt {attempt + 1})")
                    
                    # Set timeout
                    timeout = stage.config.timeout_seconds
                    output = await asyncio.wait_for(stage.execute(context), timeout=timeout)
                    
                    stage_result.output = output
                    stage_result.status = StageStatus.SUCCEEDED
                    break
                    
                except asyncio.TimeoutError:
                    error_msg = f"Stage {stage.config.name} timed out after {timeout} seconds"
                    if attempt < stage.config.retry_attempts:
                        logger.warning(f"{error_msg}, retrying...")
                        await asyncio.sleep(stage.config.retry_delay)
                    else:
                        stage_result.error = error_msg
                        stage_result.status = StageStatus.FAILED
                        
                except Exception as e:
                    error_msg = f"Stage {stage.config.name} failed: {str(e)}"
                    if attempt < stage.config.retry_attempts:
                        logger.warning(f"{error_msg}, retrying...")
                        await asyncio.sleep(stage.config.retry_delay)
                    else:
                        stage_result.error = error_msg
                        stage_result.status = StageStatus.FAILED
        
        except Exception as e:
            stage_result.error = str(e)
            stage_result.status = StageStatus.FAILED
        
        # Finalize stage result
        stage_result.end_time = datetime.now()
        stage_result.duration = (stage_result.end_time - stage_result.start_time).total_seconds()
        
        return stage_result
    
    def _group_stages_by_dependencies(self, stages: List[PipelineStage]) -> List[List[PipelineStage]]:
        """Group stages by dependency levels."""
        groups = []
        remaining_stages = list(stages)
        completed_stages: Set[str] = set()
        
        while remaining_stages:
            current_group = []
            next_remaining = []
            
            for stage in remaining_stages:
                if stage.check_dependencies(completed_stages):
                    current_group.append(stage)
                else:
                    next_remaining.append(stage)
            
            if not current_group:
                # Circular dependency or missing dependency
                raise ValueError("Circular dependency detected or missing dependency")
            
            groups.append(current_group)
            completed_stages.update(stage.config.name for stage in current_group)
            remaining_stages = next_remaining
        
        return groups
    
    def cancel_pipeline(self, run_id: str) -> bool:
        """Cancel a running pipeline."""
        if run_id in self.active_runs:
            self.active_runs[run_id].status = PipelineStatus.CANCELLED
            return True
        return False
    
    def get_pipeline_status(self, run_id: str) -> Optional[PipelineResult]:
        """Get pipeline execution status."""
        if run_id in self.active_runs:
            return self.active_runs[run_id]
        
        for result in self.execution_history:
            if result.run_id == run_id:
                return result
        
        return None
    
    def get_execution_history(self, pipeline_id: Optional[str] = None) -> List[PipelineResult]:
        """Get execution history."""
        if pipeline_id:
            return [r for r in self.execution_history if r.pipeline_id == pipeline_id]
        return list(self.execution_history)


class Pipeline:
    """Pipeline definition and management."""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.pipeline_id = f"pipeline_{uuid.uuid4().hex[:8]}"
        self.stages: List[PipelineStage] = []
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.version = "1.0.0"
    
    def add_stage(self, stage: PipelineStage) -> 'Pipeline':
        """Add a stage to the pipeline."""
        if not stage.validate_config():
            raise ValueError(f"Invalid stage configuration: {stage.config.name}")
        
        self.stages.append(stage)
        self.updated_at = datetime.now()
        return self
    
    def remove_stage(self, stage_name: str) -> bool:
        """Remove a stage from the pipeline."""
        for i, stage in enumerate(self.stages):
            if stage.config.name == stage_name:
                del self.stages[i]
                self.updated_at = datetime.now()
                return True
        return False
    
    def get_stage(self, stage_name: str) -> Optional[PipelineStage]:
        """Get a stage by name."""
        for stage in self.stages:
            if stage.config.name == stage_name:
                return stage
        return None
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate pipeline configuration."""
        errors = []
        
        # Check for duplicate stage names
        stage_names = [stage.config.name for stage in self.stages]
        if len(stage_names) != len(set(stage_names)):
            errors.append("Duplicate stage names found")
        
        # Check dependencies
        for stage in self.stages:
            for dep in stage.config.dependencies:
                if dep not in stage_names:
                    errors.append(f"Stage {stage.config.name} has unknown dependency: {dep}")
        
        # Check for circular dependencies
        if self._has_circular_dependencies():
            errors.append("Circular dependencies detected")
        
        return len(errors) == 0, errors
    
    def _has_circular_dependencies(self) -> bool:
        """Check for circular dependencies."""
        def visit(stage_name: str, visited: Set[str], rec_stack: Set[str]) -> bool:
            visited.add(stage_name)
            rec_stack.add(stage_name)
            
            stage = self.get_stage(stage_name)
            if stage:
                for dep in stage.config.dependencies:
                    if dep not in visited:
                        if visit(dep, visited, rec_stack):
                            return True
                    elif dep in rec_stack:
                        return True
            
            rec_stack.remove(stage_name)
            return False
        
        visited: Set[str] = set()
        for stage in self.stages:
            if stage.config.name not in visited:
                if visit(stage.config.name, visited, set()):
                    return True
        
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert pipeline to dictionary."""
        return {
            'pipeline_id': self.pipeline_id,
            'config': {
                'name': self.config.name,
                'description': self.config.description,
                'pipeline_type': self.config.pipeline_type.value,
                'execution_mode': self.config.execution_mode.value,
                'max_parallel_stages': self.config.max_parallel_stages,
                'timeout_seconds': self.config.timeout_seconds,
                'retry_attempts': self.config.retry_attempts,
                'retry_delay': self.config.retry_delay,
                'environment': self.config.environment,
                'notifications': self.config.notifications,
                'tags': self.config.tags
            },
            'stages': [
                {
                    'name': stage.config.name,
                    'stage_type': stage.config.stage_type,
                    'description': stage.config.description,
                    'dependencies': stage.config.dependencies,
                    'parameters': stage.config.parameters,
                    'timeout_seconds': stage.config.timeout_seconds,
                    'retry_attempts': stage.config.retry_attempts,
                    'retry_delay': stage.config.retry_delay,
                    'skip_on_failure': stage.config.skip_on_failure,
                    'condition': stage.config.condition,
                    'resources': stage.config.resources,
                    'artifacts': stage.config.artifacts
                }
                for stage in self.stages
            ],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'version': self.version
        }


class PipelineOrchestrator:
    """Main pipeline orchestration service."""
    
    def __init__(self):
        self.executor = PipelineExecutor()
        self.pipeline_templates: Dict[str, Dict[str, Any]] = {}
        self.scheduled_pipelines: Dict[str, Dict[str, Any]] = {}
    
    async def create_pipeline(self, config: PipelineConfig) -> Pipeline:
        """Create a new pipeline."""
        pipeline = Pipeline(config)
        self.executor.pipelines[pipeline.pipeline_id] = pipeline
        return pipeline
    
    async def execute_pipeline(self, pipeline_id: str, 
                             context: Optional[Dict[str, Any]] = None) -> PipelineResult:
        """Execute a pipeline by ID."""
        if pipeline_id not in self.executor.pipelines:
            raise ValueError(f"Pipeline not found: {pipeline_id}")
        
        pipeline = self.executor.pipelines[pipeline_id]
        return await self.executor.execute_pipeline(pipeline, context)
    
    def get_pipeline(self, pipeline_id: str) -> Optional[Pipeline]:
        """Get a pipeline by ID."""
        return self.executor.pipelines.get(pipeline_id)
    
    def list_pipelines(self) -> List[Pipeline]:
        """List all pipelines."""
        return list(self.executor.pipelines.values())
    
    def create_template(self, name: str, pipeline: Pipeline) -> bool:
        """Create a pipeline template."""
        self.pipeline_templates[name] = pipeline.to_dict()
        return True
    
    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a pipeline template."""
        return self.pipeline_templates.get(name)
    
    def list_templates(self) -> List[str]:
        """List available templates."""
        return list(self.pipeline_templates.keys())
    
    async def create_from_template(self, template_name: str, 
                                  config_overrides: Optional[Dict[str, Any]] = None) -> Pipeline:
        """Create a pipeline from template."""
        template = self.get_template(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_name}")
        
        # Apply overrides
        if config_overrides:
            template = dict(template)
            if 'config' in config_overrides:
                template['config'].update(config_overrides['config'])
        
        # Create pipeline config
        config_data = template['config']
        config = PipelineConfig(
            name=config_data['name'],
            description=config_data['description'],
            pipeline_type=PipelineType(config_data['pipeline_type']),
            execution_mode=ExecutionMode(config_data['execution_mode']),
            max_parallel_stages=config_data['max_parallel_stages'],
            timeout_seconds=config_data['timeout_seconds'],
            retry_attempts=config_data['retry_attempts'],
            retry_delay=config_data['retry_delay'],
            environment=config_data['environment'],
            notifications=config_data['notifications'],
            tags=config_data['tags']
        )
        
        pipeline = await self.create_pipeline(config)
        
        # Add stages
        for stage_data in template['stages']:
            stage_config = StageConfig(
                name=stage_data['name'],
                stage_type=stage_data['stage_type'],
                description=stage_data['description'],
                dependencies=stage_data['dependencies'],
                parameters=stage_data['parameters'],
                timeout_seconds=stage_data['timeout_seconds'],
                retry_attempts=stage_data['retry_attempts'],
                retry_delay=stage_data['retry_delay'],
                skip_on_failure=stage_data['skip_on_failure'],
                condition=stage_data['condition'],
                resources=stage_data['resources'],
                artifacts=stage_data['artifacts']
            )
            
            # Create appropriate stage type
            if stage_data['stage_type'] == 'data_processing':
                stage = DataProcessingStage(stage_config)
            elif stage_data['stage_type'] == 'model_training':
                stage = ModelTrainingStage(stage_config)
            elif stage_data['stage_type'] == 'model_validation':
                stage = ModelValidationStage(stage_config)
            elif stage_data['stage_type'] == 'deployment':
                stage = DeploymentStage(stage_config)
            else:
                # Generic stage
                stage = DataProcessingStage(stage_config)
            
            pipeline.add_stage(stage)
        
        return pipeline


# Convenience functions
async def create_pipeline_orchestrator() -> PipelineOrchestrator:
    """Create a pipeline orchestrator."""
    return PipelineOrchestrator()


def create_ml_pipeline_template() -> Dict[str, Any]:
    """Create a standard ML pipeline template."""
    return {
        'config': {
            'name': 'ML Training Pipeline',
            'description': 'Standard ML model training and validation pipeline',
            'pipeline_type': PipelineType.TRAINING.value,
            'execution_mode': ExecutionMode.SEQUENTIAL.value,
            'max_parallel_stages': 2,
            'timeout_seconds': 3600,
            'retry_attempts': 2,
            'retry_delay': 30.0,
            'environment': {},
            'notifications': {},
            'tags': {'type': 'ml', 'template': 'standard'}
        },
        'stages': [
            {
                'name': 'data_preprocessing',
                'stage_type': 'data_processing',
                'description': 'Preprocess training data',
                'dependencies': [],
                'parameters': {'processing_type': 'transform'},
                'timeout_seconds': 900,
                'retry_attempts': 2,
                'retry_delay': 10.0,
                'skip_on_failure': False,
                'condition': None,
                'resources': {},
                'artifacts': {}
            },
            {
                'name': 'model_training',
                'stage_type': 'model_training',
                'description': 'Train ML model',
                'dependencies': ['data_preprocessing'],
                'parameters': {'model_type': 'random_forest', 'training_time': 0.3},
                'timeout_seconds': 1800,
                'retry_attempts': 1,
                'retry_delay': 30.0,
                'skip_on_failure': False,
                'condition': None,
                'resources': {},
                'artifacts': {}
            },
            {
                'name': 'model_validation',
                'stage_type': 'model_validation',
                'description': 'Validate trained model',
                'dependencies': ['model_training'],
                'parameters': {},
                'timeout_seconds': 600,
                'retry_attempts': 2,
                'retry_delay': 10.0,
                'skip_on_failure': False,
                'condition': None,
                'resources': {},
                'artifacts': {}
            },
            {
                'name': 'model_deployment',
                'stage_type': 'deployment',
                'description': 'Deploy validated model',
                'dependencies': ['model_validation'],
                'parameters': {'deployment_config': {'replicas': 2}},
                'timeout_seconds': 900,
                'retry_attempts': 2,
                'retry_delay': 20.0,
                'skip_on_failure': True,
                'condition': None,
                'resources': {},
                'artifacts': {}
            }
        ]
    }


# Module exports
__all__ = [
    'PipelineStatus', 'StageStatus', 'ExecutionMode', 'PipelineType',
    'PipelineConfig', 'StageConfig', 'StageResult', 'PipelineResult',
    'PipelineStage', 'DataProcessingStage', 'ModelTrainingStage', 
    'ModelValidationStage', 'DeploymentStage',
    'PipelineExecutor', 'Pipeline', 'PipelineOrchestrator',
    'create_pipeline_orchestrator', 'create_ml_pipeline_template'
]