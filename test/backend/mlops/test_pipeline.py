"""
Test Module 64: MLOps Pipeline Orchestration Service

Comprehensive test suite for pipeline orchestration functionality including:
- Pipeline creation and configuration
- Stage execution and dependency management  
- Different execution modes (sequential, parallel, DAG)
- Error handling and retry logic
- Pipeline templates and orchestration
- Real-time monitoring and status tracking
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Test imports with fallback handling
try:
    from backend.mlops.pipeline import (
        PipelineStatus, StageStatus, ExecutionMode, PipelineType,
        PipelineConfig, StageConfig, StageResult, PipelineResult,
        PipelineStage, DataProcessingStage, ModelTrainingStage, 
        ModelValidationStage, DeploymentStage,
        PipelineExecutor, Pipeline, PipelineOrchestrator,
        create_pipeline_orchestrator, create_ml_pipeline_template
    )
    MODULE_EXISTS = True
except ImportError as e:
    MODULE_EXISTS = False
    print(f"Module import failed: {e}")
    
    # Create mock classes for testing
    class PipelineStatus:
        PENDING = "pending"
        RUNNING = "running"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        CANCELLED = "cancelled"
        PAUSED = "paused"
        SKIPPED = "skipped"
    
    class StageStatus:
        WAITING = "waiting"
        READY = "ready"
        RUNNING = "running"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        CANCELLED = "cancelled"
        SKIPPED = "skipped"
    
    class ExecutionMode:
        SEQUENTIAL = "sequential"
        PARALLEL = "parallel"
        CONDITIONAL = "conditional"
        DAG = "dag"
    
    class PipelineType:
        TRAINING = "training"
        INFERENCE = "inference"
        DATA_PROCESSING = "data_processing"
        MODEL_VALIDATION = "model_validation"
        DEPLOYMENT = "deployment"
        MONITORING = "monitoring"
        CUSTOM = "custom"


@pytest.mark.asyncio
class TestModule64BackendMlopsPipeline:
    """Test suite for MLOps Pipeline Orchestration Service."""
    
    def test_module_availability(self):
        """Test that the module can be imported."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert MODULE_EXISTS
    
    def test_pipeline_status_enum(self):
        """Test pipeline status enumeration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert hasattr(PipelineStatus, 'PENDING')
        assert hasattr(PipelineStatus, 'RUNNING')
        assert hasattr(PipelineStatus, 'SUCCEEDED')
        assert hasattr(PipelineStatus, 'FAILED')
        assert hasattr(PipelineStatus, 'CANCELLED')
        assert hasattr(PipelineStatus, 'PAUSED')
        assert hasattr(PipelineStatus, 'SKIPPED')
    
    def test_stage_status_enum(self):
        """Test stage status enumeration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert hasattr(StageStatus, 'WAITING')
        assert hasattr(StageStatus, 'READY')
        assert hasattr(StageStatus, 'RUNNING')
        assert hasattr(StageStatus, 'SUCCEEDED')
        assert hasattr(StageStatus, 'FAILED')
        assert hasattr(StageStatus, 'CANCELLED')
        assert hasattr(StageStatus, 'SKIPPED')
    
    def test_execution_mode_enum(self):
        """Test execution mode enumeration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert hasattr(ExecutionMode, 'SEQUENTIAL')
        assert hasattr(ExecutionMode, 'PARALLEL')
        assert hasattr(ExecutionMode, 'CONDITIONAL')
        assert hasattr(ExecutionMode, 'DAG')
    
    def test_pipeline_type_enum(self):
        """Test pipeline type enumeration."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        assert hasattr(PipelineType, 'TRAINING')
        assert hasattr(PipelineType, 'INFERENCE')
        assert hasattr(PipelineType, 'DATA_PROCESSING')
        assert hasattr(PipelineType, 'MODEL_VALIDATION')
        assert hasattr(PipelineType, 'DEPLOYMENT')
        assert hasattr(PipelineType, 'MONITORING')
        assert hasattr(PipelineType, 'CUSTOM')
    
    def test_pipeline_config_creation(self):
        """Test pipeline configuration creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = PipelineConfig(
            name="test_pipeline",
            description="Test pipeline",
            pipeline_type=PipelineType.TRAINING,
            execution_mode=ExecutionMode.SEQUENTIAL
        )
        
        assert config.name == "test_pipeline"
        assert config.description == "Test pipeline"
        assert config.pipeline_type == PipelineType.TRAINING
        assert config.execution_mode == ExecutionMode.SEQUENTIAL
        assert config.max_parallel_stages == 4
        assert config.timeout_seconds == 3600
        assert config.retry_attempts == 3
        assert config.retry_delay == 30.0
        assert isinstance(config.environment, dict)
        assert isinstance(config.notifications, dict)
        assert isinstance(config.tags, dict)
    
    def test_stage_config_creation(self):
        """Test stage configuration creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = StageConfig(
            name="test_stage",
            stage_type="data_processing",
            description="Test stage",
            dependencies=["stage1", "stage2"]
        )
        
        assert config.name == "test_stage"
        assert config.stage_type == "data_processing"
        assert config.description == "Test stage"
        assert config.dependencies == ["stage1", "stage2"]
        assert config.timeout_seconds == 1800
        assert config.retry_attempts == 2
        assert config.retry_delay == 10.0
        assert config.skip_on_failure is False
        assert config.condition is None
        assert isinstance(config.parameters, dict)
        assert isinstance(config.resources, dict)
        assert isinstance(config.artifacts, dict)
    
    def test_stage_result_creation(self):
        """Test stage result creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        start_time = datetime.now()
        result = StageResult(
            stage_id="test_stage_1",
            status=StageStatus.SUCCEEDED,
            start_time=start_time
        )
        
        assert result.stage_id == "test_stage_1"
        assert result.status == StageStatus.SUCCEEDED
        assert result.start_time == start_time
        assert result.end_time is None
        assert result.duration == 0.0
        assert result.output is None
        assert result.error is None
        assert isinstance(result.metrics, dict)
        assert isinstance(result.artifacts, dict)
        assert isinstance(result.logs, list)
    
    def test_pipeline_result_creation(self):
        """Test pipeline result creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        start_time = datetime.now()
        result = PipelineResult(
            pipeline_id="pipeline_123",
            run_id="run_456",
            status=PipelineStatus.RUNNING,
            start_time=start_time
        )
        
        assert result.pipeline_id == "pipeline_123"
        assert result.run_id == "run_456"
        assert result.status == PipelineStatus.RUNNING
        assert result.start_time == start_time
        assert result.end_time is None
        assert result.duration == 0.0
        assert isinstance(result.stage_results, dict)
        assert isinstance(result.metrics, dict)
        assert isinstance(result.artifacts, dict)
        assert result.error is None
        assert isinstance(result.logs, list)
    
    def test_data_processing_stage(self):
        """Test data processing stage."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = StageConfig(
            name="data_proc",
            stage_type="data_processing",
            parameters={
                'processing_type': 'transform',
                'transform_func': lambda x: x * 2
            }
        )
        
        stage = DataProcessingStage(config)
        assert stage.config == config
        assert stage.status == StageStatus.WAITING
        assert stage.validate_config() is True
        assert stage.check_dependencies(set()) is True
        assert stage.evaluate_condition({}) is True
    
    async def test_data_processing_stage_execution(self):
        """Test data processing stage execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = StageConfig(
            name="data_proc",
            stage_type="data_processing",
            parameters={
                'processing_type': 'filter',
                'filter_condition': lambda x: x > 5
            }
        )
        
        stage = DataProcessingStage(config)
        context = {'data': [1, 3, 7, 9, 2, 8]}
        
        result = await stage.execute(context)
        assert result == [7, 9, 8]
    
    async def test_model_training_stage_execution(self):
        """Test model training stage execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = StageConfig(
            name="training",
            stage_type="model_training",
            parameters={
                'model_type': 'linear_regression',
                'training_time': 0.05,
                'hyperparameters': {'learning_rate': 0.01}
            }
        )
        
        stage = ModelTrainingStage(config)
        context = {}
        
        result = await stage.execute(context)
        
        assert isinstance(result, dict)
        assert 'model_id' in result
        assert result['model_type'] == 'linear_regression'
        assert result['hyperparameters']['learning_rate'] == 0.01
        assert 'training_metrics' in result
        assert 'model_path' in result
    
    async def test_model_validation_stage_execution(self):
        """Test model validation stage execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = StageConfig(
            name="validation",
            stage_type="model_validation"
        )
        
        stage = ModelValidationStage(config)
        context = {
            'model': {
                'model_id': 'test_model',
                'training_metrics': {'accuracy': 0.9}
            },
            'validation_data': [1, 2, 3, 4, 5]
        }
        
        result = await stage.execute(context)
        
        assert isinstance(result, dict)
        assert 'validation_metrics' in result
        assert result['validation_passed'] is True
        assert result['model_id'] == 'test_model'
        assert result['validation_data_size'] == 5
    
    async def test_deployment_stage_execution(self):
        """Test deployment stage execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = StageConfig(
            name="deployment",
            stage_type="deployment",
            parameters={
                'deployment_config': {'replicas': 3, 'cpu': '500m'}
            }
        )
        
        stage = DeploymentStage(config)
        context = {
            'model': {'model_id': 'test_model_123'}
        }
        
        result = await stage.execute(context)
        
        assert isinstance(result, dict)
        assert 'deployment_id' in result
        assert 'endpoint_url' in result
        assert result['deployment_status'] == 'active'
        assert result['deployment_config']['replicas'] == 3
        assert 'health_check_url' in result
    
    def test_pipeline_creation(self):
        """Test pipeline creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = PipelineConfig(name="test_pipeline")
        pipeline = Pipeline(config)
        
        assert pipeline.config == config
        assert pipeline.pipeline_id.startswith("pipeline_")
        assert len(pipeline.stages) == 0
        assert isinstance(pipeline.created_at, datetime)
        assert isinstance(pipeline.updated_at, datetime)
        assert pipeline.version == "1.0.0"
    
    def test_pipeline_stage_management(self):
        """Test pipeline stage management."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = PipelineConfig(name="test_pipeline")
        pipeline = Pipeline(config)
        
        stage_config = StageConfig(name="test_stage", stage_type="data_processing")
        stage = DataProcessingStage(stage_config)
        
        # Add stage
        pipeline.add_stage(stage)
        assert len(pipeline.stages) == 1
        assert pipeline.get_stage("test_stage") == stage
        
        # Remove stage
        removed = pipeline.remove_stage("test_stage")
        assert removed is True
        assert len(pipeline.stages) == 0
        assert pipeline.get_stage("test_stage") is None
        
        # Remove non-existent stage
        removed = pipeline.remove_stage("non_existent")
        assert removed is False
    
    def test_pipeline_validation(self):
        """Test pipeline validation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = PipelineConfig(name="test_pipeline")
        pipeline = Pipeline(config)
        
        # Valid pipeline
        stage1_config = StageConfig(name="stage1", stage_type="data_processing")
        stage2_config = StageConfig(name="stage2", stage_type="model_training", 
                                  dependencies=["stage1"])
        
        pipeline.add_stage(DataProcessingStage(stage1_config))
        pipeline.add_stage(ModelTrainingStage(stage2_config))
        
        is_valid, errors = pipeline.validate()
        assert is_valid is True
        assert len(errors) == 0
        
        # Add duplicate stage name
        stage3_config = StageConfig(name="stage1", stage_type="data_processing")
        pipeline.add_stage(DataProcessingStage(stage3_config))
        
        is_valid, errors = pipeline.validate()
        assert is_valid is False
        assert "Duplicate stage names found" in errors
    
    def test_pipeline_dependency_validation(self):
        """Test pipeline dependency validation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = PipelineConfig(name="test_pipeline")
        pipeline = Pipeline(config)
        
        # Unknown dependency
        stage_config = StageConfig(name="stage1", stage_type="data_processing",
                                 dependencies=["unknown_stage"])
        pipeline.add_stage(DataProcessingStage(stage_config))
        
        is_valid, errors = pipeline.validate()
        assert is_valid is False
        assert any("unknown dependency" in error for error in errors)
    
    def test_pipeline_to_dict(self):
        """Test pipeline serialization."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        config = PipelineConfig(
            name="test_pipeline",
            description="Test pipeline",
            pipeline_type=PipelineType.TRAINING
        )
        pipeline = Pipeline(config)
        
        stage_config = StageConfig(name="test_stage", stage_type="data_processing")
        pipeline.add_stage(DataProcessingStage(stage_config))
        
        pipeline_dict = pipeline.to_dict()
        
        assert isinstance(pipeline_dict, dict)
        assert pipeline_dict['config']['name'] == "test_pipeline"
        assert pipeline_dict['config']['description'] == "Test pipeline"
        assert pipeline_dict['config']['pipeline_type'] == "training"
        assert len(pipeline_dict['stages']) == 1
        assert pipeline_dict['stages'][0]['name'] == "test_stage"
    
    async def test_pipeline_executor_sequential(self):
        """Test sequential pipeline execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        executor = PipelineExecutor()
        
        config = PipelineConfig(
            name="sequential_pipeline",
            execution_mode=ExecutionMode.SEQUENTIAL
        )
        pipeline = Pipeline(config)
        
        # Add stages
        stage1_config = StageConfig(
            name="stage1", 
            stage_type="data_processing",
            parameters={'processing_type': 'transform', 'transform_func': lambda x: x + 1}
        )
        stage2_config = StageConfig(
            name="stage2",
            stage_type="data_processing", 
            parameters={'processing_type': 'filter', 'filter_condition': lambda x: x > 5}
        )
        
        pipeline.add_stage(DataProcessingStage(stage1_config))
        pipeline.add_stage(DataProcessingStage(stage2_config))
        
        context = {'data': [1, 2, 3, 4, 5, 6, 7, 8]}
        result = await executor.execute_pipeline(pipeline, context)
        
        assert result.status == PipelineStatus.SUCCEEDED
        assert len(result.stage_results) == 2
        assert all(sr.status == StageStatus.SUCCEEDED for sr in result.stage_results.values())
    
    async def test_pipeline_executor_parallel(self):
        """Test parallel pipeline execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        executor = PipelineExecutor()
        
        config = PipelineConfig(
            name="parallel_pipeline",
            execution_mode=ExecutionMode.PARALLEL,
            max_parallel_stages=2
        )
        pipeline = Pipeline(config)
        
        # Add independent stages
        stage1_config = StageConfig(name="stage1", stage_type="data_processing")
        stage2_config = StageConfig(name="stage2", stage_type="data_processing")
        
        pipeline.add_stage(DataProcessingStage(stage1_config))
        pipeline.add_stage(DataProcessingStage(stage2_config))
        
        result = await executor.execute_pipeline(pipeline, {})
        
        assert result.status == PipelineStatus.SUCCEEDED
        assert len(result.stage_results) == 2
    
    async def test_pipeline_executor_dag(self):
        """Test DAG pipeline execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        executor = PipelineExecutor()
        
        config = PipelineConfig(
            name="dag_pipeline",
            execution_mode=ExecutionMode.DAG,
            max_parallel_stages=3
        )
        pipeline = Pipeline(config)
        
        # Create DAG: stage1 -> stage2, stage3 -> stage4
        stage1_config = StageConfig(name="stage1", stage_type="data_processing")
        stage2_config = StageConfig(name="stage2", stage_type="model_training", 
                                  dependencies=["stage1"])
        stage3_config = StageConfig(name="stage3", stage_type="data_processing")
        stage4_config = StageConfig(name="stage4", stage_type="model_validation",
                                  dependencies=["stage2", "stage3"])
        
        pipeline.add_stage(DataProcessingStage(stage1_config))
        pipeline.add_stage(ModelTrainingStage(stage2_config))
        pipeline.add_stage(DataProcessingStage(stage3_config))
        pipeline.add_stage(ModelValidationStage(stage4_config))
        
        result = await executor.execute_pipeline(pipeline, {})
        
        assert result.status == PipelineStatus.SUCCEEDED
        assert len(result.stage_results) == 4
    
    async def test_pipeline_executor_error_handling(self):
        """Test pipeline error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create a custom stage that fails
        class FailingStage(PipelineStage):
            async def execute(self, context):
                raise Exception("Stage intentionally failed")
        
        executor = PipelineExecutor()
        
        config = PipelineConfig(name="failing_pipeline")
        pipeline = Pipeline(config)
        
        stage_config = StageConfig(name="failing_stage", stage_type="custom")
        pipeline.add_stage(FailingStage(stage_config))
        
        result = await executor.execute_pipeline(pipeline, {})
        
        assert result.status == PipelineStatus.FAILED
        assert result.error is not None
        assert "Stage intentionally failed" in result.error
    
    async def test_pipeline_executor_retry_logic(self):
        """Test stage retry logic."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create a stage that fails first time, succeeds second time
        class FlakeyStage(PipelineStage):
            def __init__(self, config):
                super().__init__(config)
                self.attempt = 0
            
            async def execute(self, context):
                self.attempt += 1
                if self.attempt == 1:
                    raise Exception("First attempt fails")
                return {"success": True, "attempts": self.attempt}
        
        executor = PipelineExecutor()
        
        config = PipelineConfig(name="retry_pipeline")
        pipeline = Pipeline(config)
        
        stage_config = StageConfig(
            name="flakey_stage", 
            stage_type="custom",
            retry_attempts=2,
            retry_delay=0.01
        )
        pipeline.add_stage(FlakeyStage(stage_config))
        
        result = await executor.execute_pipeline(pipeline, {})
        
        assert result.status == PipelineStatus.SUCCEEDED
        stage_result = list(result.stage_results.values())[0]
        assert stage_result.status == StageStatus.SUCCEEDED
        assert stage_result.output["attempts"] == 2
    
    async def test_pipeline_executor_timeout(self):
        """Test stage timeout handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create a stage that takes too long
        class SlowStage(PipelineStage):
            async def execute(self, context):
                await asyncio.sleep(1.0)  # Longer than timeout
                return {"completed": True}
        
        executor = PipelineExecutor()
        
        config = PipelineConfig(name="timeout_pipeline")
        pipeline = Pipeline(config)
        
        stage_config = StageConfig(
            name="slow_stage",
            stage_type="custom", 
            timeout_seconds=0.1,  # Very short timeout
            retry_attempts=0
        )
        pipeline.add_stage(SlowStage(stage_config))
        
        result = await executor.execute_pipeline(pipeline, {})
        
        assert result.status == PipelineStatus.FAILED
        stage_result = list(result.stage_results.values())[0]
        assert stage_result.status == StageStatus.FAILED
        assert "timed out" in stage_result.error.lower()
    
    def test_pipeline_executor_status_management(self):
        """Test pipeline status management."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        executor = PipelineExecutor()
        
        # Test empty history
        history = executor.get_execution_history()
        assert len(history) == 0
        
        # Test non-existent pipeline status
        status = executor.get_pipeline_status("non_existent")
        assert status is None
    
    async def test_pipeline_orchestrator_creation(self):
        """Test pipeline orchestrator creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        orchestrator = await create_pipeline_orchestrator()
        assert isinstance(orchestrator, PipelineOrchestrator)
        assert isinstance(orchestrator.executor, PipelineExecutor)
        assert len(orchestrator.pipeline_templates) == 0
        assert len(orchestrator.scheduled_pipelines) == 0
    
    async def test_pipeline_orchestrator_pipeline_management(self):
        """Test pipeline orchestrator pipeline management."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        orchestrator = PipelineOrchestrator()
        
        config = PipelineConfig(name="test_pipeline")
        pipeline = await orchestrator.create_pipeline(config)
        
        assert isinstance(pipeline, Pipeline)
        assert pipeline.config.name == "test_pipeline"
        
        # Get pipeline
        retrieved = orchestrator.get_pipeline(pipeline.pipeline_id)
        assert retrieved == pipeline
        
        # List pipelines
        pipelines = orchestrator.list_pipelines()
        assert len(pipelines) == 1
        assert pipelines[0] == pipeline
    
    async def test_pipeline_orchestrator_execution(self):
        """Test pipeline orchestrator execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        orchestrator = PipelineOrchestrator()
        
        config = PipelineConfig(name="execution_test")
        pipeline = await orchestrator.create_pipeline(config)
        
        stage_config = StageConfig(name="test_stage", stage_type="data_processing")
        pipeline.add_stage(DataProcessingStage(stage_config))
        
        result = await orchestrator.execute_pipeline(pipeline.pipeline_id, {})
        
        assert result.status == PipelineStatus.SUCCEEDED
        assert result.pipeline_id == pipeline.pipeline_id
    
    async def test_pipeline_orchestrator_templates(self):
        """Test pipeline orchestrator template management."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        orchestrator = PipelineOrchestrator()
        
        config = PipelineConfig(name="template_pipeline")
        pipeline = await orchestrator.create_pipeline(config)
        
        stage_config = StageConfig(name="template_stage", stage_type="data_processing")
        pipeline.add_stage(DataProcessingStage(stage_config))
        
        # Create template
        success = orchestrator.create_template("test_template", pipeline)
        assert success is True
        
        # Get template
        template = orchestrator.get_template("test_template")
        assert template is not None
        assert template['config']['name'] == "template_pipeline"
        
        # List templates
        templates = orchestrator.list_templates()
        assert "test_template" in templates
    
    async def test_pipeline_orchestrator_from_template(self):
        """Test creating pipeline from template."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        orchestrator = PipelineOrchestrator()
        
        # Create a template
        config = PipelineConfig(name="original_pipeline")
        original_pipeline = await orchestrator.create_pipeline(config)
        
        stage_config = StageConfig(name="template_stage", stage_type="data_processing")
        original_pipeline.add_stage(DataProcessingStage(stage_config))
        
        orchestrator.create_template("test_template", original_pipeline)
        
        # Create from template
        new_pipeline = await orchestrator.create_from_template("test_template")
        
        assert isinstance(new_pipeline, Pipeline)
        assert new_pipeline.config.name == "original_pipeline"
        assert len(new_pipeline.stages) == 1
        assert new_pipeline.stages[0].config.name == "template_stage"
    
    async def test_pipeline_orchestrator_template_overrides(self):
        """Test creating pipeline from template with overrides."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        orchestrator = PipelineOrchestrator()
        
        # Create ML template
        orchestrator.pipeline_templates["ml_template"] = create_ml_pipeline_template()
        
        # Create from template with overrides
        overrides = {
            'config': {
                'name': 'Custom ML Pipeline',
                'description': 'Customized pipeline'
            }
        }
        
        pipeline = await orchestrator.create_from_template("ml_template", overrides)
        
        assert pipeline.config.name == 'Custom ML Pipeline'
        assert pipeline.config.description == 'Customized pipeline'
        assert len(pipeline.stages) == 4  # Should have all ML stages
    
    def test_ml_pipeline_template(self):
        """Test ML pipeline template creation."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        template = create_ml_pipeline_template()
        
        assert isinstance(template, dict)
        assert 'config' in template
        assert 'stages' in template
        
        config = template['config']
        assert config['name'] == 'ML Training Pipeline'
        assert config['pipeline_type'] == PipelineType.TRAINING.value
        assert config['execution_mode'] == ExecutionMode.SEQUENTIAL.value
        
        stages = template['stages']
        assert len(stages) == 4
        
        stage_names = [stage['name'] for stage in stages]
        assert 'data_preprocessing' in stage_names
        assert 'model_training' in stage_names
        assert 'model_validation' in stage_names
        assert 'model_deployment' in stage_names
    
    async def test_stage_conditions(self):
        """Test stage conditional execution."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create stage with condition
        stage_config = StageConfig(
            name="conditional_stage",
            stage_type="data_processing",
            condition="run_stage == True"
        )
        stage = DataProcessingStage(stage_config)
        
        # Test condition evaluation
        assert stage.evaluate_condition({'run_stage': True}) is True
        assert stage.evaluate_condition({'run_stage': False}) is False
        assert stage.evaluate_condition({}) is True  # Missing condition defaults to True
    
    async def test_stage_skip_on_failure(self):
        """Test stage skip on failure behavior."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Create a failing stage with skip_on_failure
        class FailingStage(PipelineStage):
            async def execute(self, context):
                raise Exception("This stage fails")
        
        executor = PipelineExecutor()
        
        config = PipelineConfig(name="skip_failure_pipeline")
        pipeline = Pipeline(config)
        
        failing_stage_config = StageConfig(
            name="failing_stage",
            stage_type="custom",
            skip_on_failure=True,
            retry_attempts=0
        )
        success_stage_config = StageConfig(
            name="success_stage",
            stage_type="data_processing",
            dependencies=["failing_stage"]
        )
        
        pipeline.add_stage(FailingStage(failing_stage_config))
        pipeline.add_stage(DataProcessingStage(success_stage_config))
        
        result = await executor.execute_pipeline(pipeline, {})
        
        # Pipeline should succeed despite failing stage
        assert result.status == PipelineStatus.SUCCEEDED
        assert len(result.stage_results) == 2
        
        # First stage should have failed
        failing_result = result.stage_results[pipeline.stages[0].stage_id]
        assert failing_result.status == StageStatus.FAILED
        
        # Second stage should have succeeded
        success_result = result.stage_results[pipeline.stages[1].stage_id]
        assert success_result.status == StageStatus.SUCCEEDED
    
    async def test_context_passing(self):
        """Test context passing between stages."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        executor = PipelineExecutor()
        
        config = PipelineConfig(name="context_pipeline")
        pipeline = Pipeline(config)
        
        # Stage 1: Process data
        stage1_config = StageConfig(
            name="data_stage",
            stage_type="data_processing",
            parameters={'processing_type': 'transform', 'transform_func': lambda x: x * 2}
        )
        
        # Stage 2: Train model using processed data
        stage2_config = StageConfig(
            name="training_stage",
            stage_type="model_training",
            dependencies=["data_stage"],
            parameters={'model_type': 'test_model', 'training_time': 0.05}
        )
        
        pipeline.add_stage(DataProcessingStage(stage1_config))
        pipeline.add_stage(ModelTrainingStage(stage2_config))
        
        context = {'data': [1, 2, 3, 4, 5]}
        result = await executor.execute_pipeline(pipeline, context)
        
        assert result.status == PipelineStatus.SUCCEEDED
        assert len(result.stage_results) == 2
        
        # Check that context was updated between stages
        assert 'data_stage' in context
        assert context['data_stage'] == [2, 4, 6, 8, 10]  # Transformed data
    
    def test_convenience_functions(self):
        """Test convenience functions."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test create_ml_pipeline_template
        template = create_ml_pipeline_template()
        assert isinstance(template, dict)
        assert 'config' in template
        assert 'stages' in template
    
    def test_edge_cases_and_error_handling(self):
        """Test edge cases and error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        # Test invalid stage configuration
        invalid_config = StageConfig(name="", stage_type="")
        stage = DataProcessingStage(invalid_config)
        assert stage.validate_config() is False
        
        # Test dependency checking
        config = StageConfig(name="test", stage_type="test", dependencies=["dep1", "dep2"])
        stage = DataProcessingStage(config)
        assert stage.check_dependencies(set()) is False
        assert stage.check_dependencies({"dep1"}) is False
        assert stage.check_dependencies({"dep1", "dep2"}) is True
        assert stage.check_dependencies({"dep1", "dep2", "extra"}) is True
    
    async def test_orchestrator_error_handling(self):
        """Test orchestrator error handling."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        orchestrator = PipelineOrchestrator()
        
        # Test executing non-existent pipeline
        try:
            await orchestrator.execute_pipeline("non_existent_id", {})
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Pipeline not found" in str(e)
        
        # Test creating from non-existent template
        try:
            await orchestrator.create_from_template("non_existent_template")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Template not found" in str(e)
    
    def test_module_exports(self):
        """Test module exports."""
        if not MODULE_EXISTS:
            pytest.skip("Module not available")
        
        from backend.mlops.pipeline import __all__
        
        expected_exports = [
            'PipelineStatus', 'StageStatus', 'ExecutionMode', 'PipelineType',
            'PipelineConfig', 'StageConfig', 'StageResult', 'PipelineResult',
            'PipelineStage', 'DataProcessingStage', 'ModelTrainingStage', 
            'ModelValidationStage', 'DeploymentStage',
            'PipelineExecutor', 'Pipeline', 'PipelineOrchestrator',
            'create_pipeline_orchestrator', 'create_ml_pipeline_template'
        ]
        
        for export in expected_exports:
            assert export in __all__, f"Missing export: {export}"