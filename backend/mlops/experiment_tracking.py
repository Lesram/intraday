"""
MLOps Experiment Tracking Service

Comprehensive experiment tracking system providing:
- Experiment management and organization
- Run tracking with parameters, metrics, and artifacts
- Model comparison and analysis
- Hyperparameter optimization integration
- Artifact storage and versioning
- Collaborative experiment sharing
- Real-time monitoring and notifications
- Integration with popular ML frameworks

Author: MLOps Team
Created: 2025-01-01
Version: 1.0.0
"""

import json
import hashlib
import shutil
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExperimentStatus(str, Enum):
    """Experiment status enumeration."""
    CREATED = "created"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class RunStatus(str, Enum):
    """Run status enumeration."""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    KILLED = "killed"


class ArtifactType(str, Enum):
    """Artifact type enumeration."""
    MODEL = "model"
    DATASET = "dataset"
    PLOT = "plot"
    METRICS = "metrics"
    LOGS = "logs"
    CONFIG = "config"
    WEIGHTS = "weights"
    CHECKPOINT = "checkpoint"
    PREDICTION = "prediction"
    REPORT = "report"
    OTHER = "other"


class MetricType(str, Enum):
    """Metric type enumeration."""
    SCALAR = "scalar"
    VECTOR = "vector"
    HISTOGRAM = "histogram"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TEXT = "text"
    TABLE = "table"


@dataclass
class Parameter:
    """Parameter representation."""
    name: str
    value: Any
    type: str = "string"
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert parameter to dictionary."""
        return {
            'name': self.name,
            'value': self.value,
            'type': self.type,
            'description': self.description,
            'created_at': self.created_at.isoformat()
        }


@dataclass
class Metric:
    """Metric representation."""
    name: str
    value: Any
    step: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    type: MetricType = MetricType.SCALAR
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metric to dictionary."""
        return {
            'name': self.name,
            'value': self.value,
            'step': self.step,
            'timestamp': self.timestamp.isoformat(),
            'type': self.type.value,
            'metadata': self.metadata
        }


@dataclass
class Artifact:
    """Artifact representation."""
    name: str
    path: str
    type: ArtifactType = ArtifactType.OTHER
    size: int = 0
    checksum: str = ""
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Calculate artifact details after initialization."""
        if Path(self.path).exists():
            self.size = Path(self.path).stat().st_size
            self.checksum = self._calculate_checksum()
    
    def _calculate_checksum(self) -> str:
        """Calculate file checksum."""
        try:
            hash_algo = hashlib.sha256()
            with open(self.path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_algo.update(chunk)
            return hash_algo.hexdigest()
        except Exception as e:
            logger.warning(f"Failed to calculate checksum for {self.path}: {e}")
            return ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert artifact to dictionary."""
        return {
            'name': self.name,
            'path': self.path,
            'type': self.type.value,
            'size': self.size,
            'checksum': self.checksum,
            'description': self.description,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat()
        }


@dataclass
class ExperimentRun:
    """Experiment run representation."""
    id: str
    experiment_id: str
    name: str = ""
    status: RunStatus = RunStatus.CREATED
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    parameters: Dict[str, Parameter] = field(default_factory=dict)
    metrics: Dict[str, List[Metric]] = field(default_factory=dict)
    artifacts: Dict[str, Artifact] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)
    notes: str = ""
    source_version: str = ""
    entry_point: str = ""
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def duration(self) -> Optional[timedelta]:
        """Calculate run duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        elif self.start_time:
            return datetime.now() - self.start_time
        return None
    
    @property
    def is_active(self) -> bool:
        """Check if run is active."""
        return self.status in [RunStatus.CREATED, RunStatus.RUNNING]
    
    def start(self):
        """Start the run."""
        self.status = RunStatus.RUNNING
        self.start_time = datetime.now()
        self.updated_at = datetime.now()
    
    def finish(self, status: RunStatus = RunStatus.COMPLETED):
        """Finish the run."""
        self.status = status
        self.end_time = datetime.now()
        self.updated_at = datetime.now()
    
    def log_parameter(self, name: str, value: Any, description: str = ""):
        """Log a parameter."""
        param_type = type(value).__name__
        self.parameters[name] = Parameter(
            name=name,
            value=value,
            type=param_type,
            description=description
        )
        self.updated_at = datetime.now()
    
    def log_metric(self, name: str, value: Any, step: int = 0, 
                   metric_type: MetricType = MetricType.SCALAR):
        """Log a metric."""
        if name not in self.metrics:
            self.metrics[name] = []
        
        metric = Metric(
            name=name,
            value=value,
            step=step,
            type=metric_type
        )
        self.metrics[name].append(metric)
        self.updated_at = datetime.now()
    
    def log_artifact(self, name: str, path: str, artifact_type: ArtifactType = ArtifactType.OTHER,
                     description: str = "", metadata: Optional[Dict[str, Any]] = None):
        """Log an artifact."""
        if metadata is None:
            metadata = {}
        
        artifact = Artifact(
            name=name,
            path=path,
            type=artifact_type,
            description=description,
            metadata=metadata
        )
        self.artifacts[name] = artifact
        self.updated_at = datetime.now()
    
    def add_tag(self, key: str, value: str):
        """Add a tag."""
        self.tags[key] = value
        self.updated_at = datetime.now()
    
    def remove_tag(self, key: str) -> bool:
        """Remove a tag."""
        if key in self.tags:
            del self.tags[key]
            self.updated_at = datetime.now()
            return True
        return False
    
    def get_latest_metric(self, name: str) -> Optional[Metric]:
        """Get the latest value of a metric."""
        if name in self.metrics and self.metrics[name]:
            return max(self.metrics[name], key=lambda m: m.step)
        return None
    
    def get_metric_history(self, name: str) -> List[Metric]:
        """Get metric history."""
        return self.metrics.get(name, [])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert run to dictionary."""
        return {
            'id': self.id,
            'experiment_id': self.experiment_id,
            'name': self.name,
            'status': self.status.value,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration': str(self.duration) if self.duration else None,
            'parameters': {k: v.to_dict() for k, v in self.parameters.items()},
            'metrics': {k: [m.to_dict() for m in v] for k, v in self.metrics.items()},
            'artifacts': {k: v.to_dict() for k, v in self.artifacts.items()},
            'tags': self.tags,
            'notes': self.notes,
            'source_version': self.source_version,
            'entry_point': self.entry_point,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


@dataclass
class Experiment:
    """Experiment representation."""
    id: str
    name: str
    description: str = ""
    status: ExperimentStatus = ExperimentStatus.CREATED
    tags: Dict[str, str] = field(default_factory=dict)
    artifact_location: str = ""
    lifecycle_stage: str = "active"
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert experiment to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'status': self.status.value,
            'tags': self.tags,
            'artifact_location': self.artifact_location,
            'lifecycle_stage': self.lifecycle_stage,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class ExperimentComparator:
    """Compare experiments and runs."""
    
    def __init__(self):
        self.comparison_cache = {}
    
    def compare_runs(self, run_ids: List[str], tracker: 'ExperimentTracker') -> Dict[str, Any]:
        """Compare multiple runs."""
        runs = []
        for run_id in run_ids:
            run = tracker.get_run(run_id)
            if run:
                runs.append(run)
        
        if not runs:
            return {}
        
        comparison = {
            'runs': [run.to_dict() for run in runs],
            'parameter_comparison': self._compare_parameters(runs),
            'metric_comparison': self._compare_metrics(runs),
            'summary': self._generate_comparison_summary(runs)
        }
        
        return comparison
    
    def _compare_parameters(self, runs: List[ExperimentRun]) -> Dict[str, Any]:
        """Compare parameters across runs."""
        all_params = set()
        for run in runs:
            all_params.update(run.parameters.keys())
        
        comparison = {}
        for param_name in all_params:
            values = []
            for run in runs:
                if param_name in run.parameters:
                    values.append({
                        'run_id': run.id,
                        'value': run.parameters[param_name].value,
                        'type': run.parameters[param_name].type
                    })
                else:
                    values.append({
                        'run_id': run.id,
                        'value': None,
                        'type': None
                    })
            comparison[param_name] = values
        
        return comparison
    
    def _compare_metrics(self, runs: List[ExperimentRun]) -> Dict[str, Any]:
        """Compare metrics across runs."""
        all_metrics = set()
        for run in runs:
            all_metrics.update(run.metrics.keys())
        
        comparison = {}
        for metric_name in all_metrics:
            values = []
            for run in runs:
                if metric_name in run.metrics:
                    latest_metric = run.get_latest_metric(metric_name)
                    values.append({
                        'run_id': run.id,
                        'value': latest_metric.value if latest_metric else None,
                        'step': latest_metric.step if latest_metric else None,
                        'history_length': len(run.metrics[metric_name])
                    })
                else:
                    values.append({
                        'run_id': run.id,
                        'value': None,
                        'step': None,
                        'history_length': 0
                    })
            comparison[metric_name] = values
        
        return comparison
    
    def _generate_comparison_summary(self, runs: List[ExperimentRun]) -> Dict[str, Any]:
        """Generate comparison summary."""
        total_runs = len(runs)
        completed_runs = sum(1 for run in runs if run.status == RunStatus.COMPLETED)
        failed_runs = sum(1 for run in runs if run.status == RunStatus.FAILED)
        
        durations = [run.duration for run in runs if run.duration]
        avg_duration = sum(durations, timedelta()) / len(durations) if durations else None
        
        return {
            'total_runs': total_runs,
            'completed_runs': completed_runs,
            'failed_runs': failed_runs,
            'success_rate': completed_runs / total_runs if total_runs > 0 else 0,
            'average_duration': str(avg_duration) if avg_duration else None,
            'date_range': {
                'earliest': min(run.created_at for run in runs).isoformat(),
                'latest': max(run.created_at for run in runs).isoformat()
            }
        }
    
    def find_best_run(self, experiment_id: str, metric_name: str, 
                      tracker: 'ExperimentTracker', maximize: bool = True) -> Optional[ExperimentRun]:
        """Find best run based on a metric."""
        runs = tracker.list_runs(experiment_id)
        if not runs:
            return None
        
        runs_with_metric = []
        for run in runs:
            latest_metric = run.get_latest_metric(metric_name)
            if latest_metric and latest_metric.value is not None:
                runs_with_metric.append((run, latest_metric.value))
        
        if not runs_with_metric:
            return None
        
        if maximize:
            best_run, _ = max(runs_with_metric, key=lambda x: x[1])
        else:
            best_run, _ = min(runs_with_metric, key=lambda x: x[1])
        
        return best_run


class ArtifactManager:
    """Manage experiment artifacts."""
    
    def __init__(self, base_path: str = "./artifacts"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def store_artifact(self, experiment_id: str, run_id: str, 
                      artifact: Artifact, copy_file: bool = True) -> str:
        """Store an artifact."""
        # Create directory structure
        artifact_dir = self.base_path / experiment_id / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        source_path = Path(artifact.path)
        if copy_file and source_path.exists():
            # Copy file to artifact storage
            dest_path = artifact_dir / source_path.name
            shutil.copy2(source_path, dest_path)
            artifact.path = str(dest_path)
        
        # Store artifact metadata
        metadata_path = artifact_dir / f"{artifact.name}.json"
        with open(metadata_path, 'w') as f:
            json.dump(artifact.to_dict(), f, indent=2)
        
        return artifact.path
    
    def retrieve_artifact(self, experiment_id: str, run_id: str, 
                         artifact_name: str) -> Optional[Artifact]:
        """Retrieve an artifact."""
        metadata_path = self.base_path / experiment_id / run_id / f"{artifact_name}.json"
        
        if not metadata_path.exists():
            return None
        
        try:
            with open(metadata_path, 'r') as f:
                data = json.load(f)
            
            artifact = Artifact(
                name=data['name'],
                path=data['path'],
                type=ArtifactType(data['type']),
                size=data['size'],
                checksum=data['checksum'],
                description=data.get('description', ''),
                metadata=data.get('metadata', {}),
                created_at=datetime.fromisoformat(data['created_at'])
            )
            
            return artifact
        except Exception as e:
            logger.error(f"Failed to retrieve artifact {artifact_name}: {e}")
            return None
    
    def list_artifacts(self, experiment_id: str, run_id: str) -> List[Artifact]:
        """List all artifacts for a run."""
        artifact_dir = self.base_path / experiment_id / run_id
        if not artifact_dir.exists():
            return []
        
        artifacts = []
        for metadata_file in artifact_dir.glob("*.json"):
            artifact_name = metadata_file.stem
            artifact = self.retrieve_artifact(experiment_id, run_id, artifact_name)
            if artifact:
                artifacts.append(artifact)
        
        return artifacts
    
    def delete_artifact(self, experiment_id: str, run_id: str, 
                       artifact_name: str) -> bool:
        """Delete an artifact."""
        try:
            artifact_dir = self.base_path / experiment_id / run_id
            
            # Delete metadata file
            metadata_path = artifact_dir / f"{artifact_name}.json"
            if metadata_path.exists():
                metadata_path.unlink()
            
            # Delete actual file if it exists in our storage
            for file_path in artifact_dir.glob(f"{artifact_name}.*"):
                if file_path.suffix != '.json':
                    file_path.unlink()
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete artifact {artifact_name}: {e}")
            return False


class ExperimentTracker:
    """Main experiment tracking system."""
    
    def __init__(self, storage_path: str = "./experiments"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.experiments: Dict[str, Experiment] = {}
        self.runs: Dict[str, ExperimentRun] = {}
        self.comparator = ExperimentComparator()
        self.artifact_manager = ArtifactManager(str(self.storage_path / "artifacts"))
        
        self._load_experiments()
        self._load_runs()
    
    def _generate_id(self, prefix: str = "") -> str:
        """Generate unique ID."""
        timestamp = str(int(time.time() * 1000))
        return f"{prefix}_{timestamp}" if prefix else timestamp
    
    def _save_experiment(self, experiment: Experiment):
        """Save experiment to storage."""
        exp_file = self.storage_path / f"experiment_{experiment.id}.json"
        with open(exp_file, 'w') as f:
            json.dump(experiment.to_dict(), f, indent=2)
    
    def _save_run(self, run: ExperimentRun):
        """Save run to storage."""
        run_file = self.storage_path / f"run_{run.id}.json"
        with open(run_file, 'w') as f:
            json.dump(run.to_dict(), f, indent=2)
    
    def _load_experiments(self):
        """Load experiments from storage."""
        for exp_file in self.storage_path.glob("experiment_*.json"):
            try:
                with open(exp_file, 'r') as f:
                    data = json.load(f)
                
                experiment = Experiment(
                    id=data['id'],
                    name=data['name'],
                    description=data.get('description', ''),
                    status=ExperimentStatus(data['status']),
                    tags=data.get('tags', {}),
                    artifact_location=data.get('artifact_location', ''),
                    lifecycle_stage=data.get('lifecycle_stage', 'active'),
                    created_by=data.get('created_by', ''),
                    created_at=datetime.fromisoformat(data['created_at']),
                    updated_at=datetime.fromisoformat(data['updated_at'])
                )
                
                self.experiments[experiment.id] = experiment
            except Exception as e:
                logger.error(f"Failed to load experiment from {exp_file}: {e}")
    
    def _load_runs(self):
        """Load runs from storage."""
        for run_file in self.storage_path.glob("run_*.json"):
            try:
                with open(run_file, 'r') as f:
                    data = json.load(f)
                
                # Reconstruct parameters
                parameters = {}
                for name, param_data in data.get('parameters', {}).items():
                    parameters[name] = Parameter(
                        name=param_data['name'],
                        value=param_data['value'],
                        type=param_data['type'],
                        description=param_data.get('description', ''),
                        created_at=datetime.fromisoformat(param_data['created_at'])
                    )
                
                # Reconstruct metrics
                metrics = {}
                for name, metric_list in data.get('metrics', {}).items():
                    metrics[name] = []
                    for metric_data in metric_list:
                        metric = Metric(
                            name=metric_data['name'],
                            value=metric_data['value'],
                            step=metric_data['step'],
                            timestamp=datetime.fromisoformat(metric_data['timestamp']),
                            type=MetricType(metric_data['type']),
                            metadata=metric_data.get('metadata', {})
                        )
                        metrics[name].append(metric)
                
                # Reconstruct artifacts
                artifacts = {}
                for name, artifact_data in data.get('artifacts', {}).items():
                    artifact = Artifact(
                        name=artifact_data['name'],
                        path=artifact_data['path'],
                        type=ArtifactType(artifact_data['type']),
                        size=artifact_data['size'],
                        checksum=artifact_data['checksum'],
                        description=artifact_data.get('description', ''),
                        metadata=artifact_data.get('metadata', {}),
                        created_at=datetime.fromisoformat(artifact_data['created_at'])
                    )
                    artifacts[name] = artifact
                
                run = ExperimentRun(
                    id=data['id'],
                    experiment_id=data['experiment_id'],
                    name=data.get('name', ''),
                    status=RunStatus(data['status']),
                    start_time=datetime.fromisoformat(data['start_time']) if data.get('start_time') else None,
                    end_time=datetime.fromisoformat(data['end_time']) if data.get('end_time') else None,
                    parameters=parameters,
                    metrics=metrics,
                    artifacts=artifacts,
                    tags=data.get('tags', {}),
                    notes=data.get('notes', ''),
                    source_version=data.get('source_version', ''),
                    entry_point=data.get('entry_point', ''),
                    created_by=data.get('created_by', ''),
                    created_at=datetime.fromisoformat(data['created_at']),
                    updated_at=datetime.fromisoformat(data['updated_at'])
                )
                
                self.runs[run.id] = run
            except Exception as e:
                logger.error(f"Failed to load run from {run_file}: {e}")
    
    def create_experiment(self, name: str, description: str = "", 
                         tags: Optional[Dict[str, str]] = None,
                         artifact_location: str = "", created_by: str = "") -> Experiment:
        """Create a new experiment."""
        if tags is None:
            tags = {}
        
        experiment_id = self._generate_id("exp")
        
        experiment = Experiment(
            id=experiment_id,
            name=name,
            description=description,
            tags=tags,
            artifact_location=artifact_location or str(self.storage_path / "artifacts" / experiment_id),
            created_by=created_by
        )
        
        self.experiments[experiment_id] = experiment
        self._save_experiment(experiment)
        
        logger.info(f"Created experiment: {experiment_id}")
        return experiment
    
    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Get an experiment by ID."""
        return self.experiments.get(experiment_id)
    
    def get_experiment_by_name(self, name: str) -> Optional[Experiment]:
        """Get an experiment by name."""
        for experiment in self.experiments.values():
            if experiment.name == name:
                return experiment
        return None
    
    def list_experiments(self, status: Optional[ExperimentStatus] = None) -> List[Experiment]:
        """List experiments."""
        experiments = list(self.experiments.values())
        if status:
            experiments = [exp for exp in experiments if exp.status == status]
        return sorted(experiments, key=lambda x: x.created_at, reverse=True)
    
    def update_experiment(self, experiment_id: str, **kwargs) -> bool:
        """Update an experiment."""
        if experiment_id not in self.experiments:
            return False
        
        experiment = self.experiments[experiment_id]
        
        for key, value in kwargs.items():
            if hasattr(experiment, key):
                setattr(experiment, key, value)
        
        experiment.updated_at = datetime.now()
        self._save_experiment(experiment)
        return True
    
    def delete_experiment(self, experiment_id: str) -> bool:
        """Delete an experiment and all its runs."""
        if experiment_id not in self.experiments:
            return False
        
        # Delete all runs for this experiment
        runs_to_delete = [run_id for run_id, run in self.runs.items() 
                         if run.experiment_id == experiment_id]
        for run_id in runs_to_delete:
            self.delete_run(run_id)
        
        # Delete experiment
        del self.experiments[experiment_id]
        
        # Delete experiment file
        exp_file = self.storage_path / f"experiment_{experiment_id}.json"
        if exp_file.exists():
            exp_file.unlink()
        
        logger.info(f"Deleted experiment: {experiment_id}")
        return True
    
    def create_run(self, experiment_id: str, name: str = "", 
                  tags: Optional[Dict[str, str]] = None,
                  source_version: str = "", entry_point: str = "",
                  created_by: str = "") -> Optional[ExperimentRun]:
        """Create a new run."""
        if experiment_id not in self.experiments:
            logger.error(f"Experiment {experiment_id} not found")
            return None
        
        if tags is None:
            tags = {}
        
        run_id = self._generate_id("run")
        
        run = ExperimentRun(
            id=run_id,
            experiment_id=experiment_id,
            name=name or f"Run {run_id}",
            tags=tags,
            source_version=source_version,
            entry_point=entry_point,
            created_by=created_by
        )
        
        self.runs[run_id] = run
        self._save_run(run)
        
        logger.info(f"Created run: {run_id} for experiment: {experiment_id}")
        return run
    
    def get_run(self, run_id: str) -> Optional[ExperimentRun]:
        """Get a run by ID."""
        return self.runs.get(run_id)
    
    def list_runs(self, experiment_id: Optional[str] = None,
                 status: Optional[RunStatus] = None) -> List[ExperimentRun]:
        """List runs."""
        runs = list(self.runs.values())
        
        if experiment_id:
            runs = [run for run in runs if run.experiment_id == experiment_id]
        
        if status:
            runs = [run for run in runs if run.status == status]
        
        return sorted(runs, key=lambda x: x.created_at, reverse=True)
    
    def update_run(self, run_id: str, **kwargs) -> bool:
        """Update a run."""
        if run_id not in self.runs:
            return False
        
        run = self.runs[run_id]
        
        for key, value in kwargs.items():
            if hasattr(run, key):
                setattr(run, key, value)
        
        run.updated_at = datetime.now()
        self._save_run(run)
        return True
    
    def delete_run(self, run_id: str) -> bool:
        """Delete a run."""
        if run_id not in self.runs:
            return False
        
        run = self.runs[run_id]
        
        # Delete run artifacts
        artifacts = self.artifact_manager.list_artifacts(run.experiment_id, run_id)
        for artifact in artifacts:
            self.artifact_manager.delete_artifact(run.experiment_id, run_id, artifact.name)
        
        # Delete run
        del self.runs[run_id]
        
        # Delete run file
        run_file = self.storage_path / f"run_{run_id}.json"
        if run_file.exists():
            run_file.unlink()
        
        logger.info(f"Deleted run: {run_id}")
        return True
    
    def start_run(self, run_id: str) -> bool:
        """Start a run."""
        if run_id not in self.runs:
            return False
        
        run = self.runs[run_id]
        run.start()
        self._save_run(run)
        return True
    
    def finish_run(self, run_id: str, status: RunStatus = RunStatus.COMPLETED) -> bool:
        """Finish a run."""
        if run_id not in self.runs:
            return False
        
        run = self.runs[run_id]
        run.finish(status)
        self._save_run(run)
        return True
    
    def log_parameter(self, run_id: str, name: str, value: Any, description: str = "") -> bool:
        """Log a parameter to a run."""
        if run_id not in self.runs:
            return False
        
        run = self.runs[run_id]
        run.log_parameter(name, value, description)
        self._save_run(run)
        return True
    
    def log_metric(self, run_id: str, name: str, value: Any, step: int = 0,
                  metric_type: MetricType = MetricType.SCALAR) -> bool:
        """Log a metric to a run."""
        if run_id not in self.runs:
            return False
        
        run = self.runs[run_id]
        run.log_metric(name, value, step, metric_type)
        self._save_run(run)
        return True
    
    def log_artifact(self, run_id: str, name: str, path: str,
                    artifact_type: ArtifactType = ArtifactType.OTHER,
                    description: str = "", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Log an artifact to a run."""
        if run_id not in self.runs:
            return False
        
        run = self.runs[run_id]
        artifact = Artifact(
            name=name,
            path=path,
            type=artifact_type,
            description=description,
            metadata=metadata or {}
        )
        
        # Store artifact
        self.artifact_manager.store_artifact(run.experiment_id, run_id, artifact)
        
        # Log to run
        run.log_artifact(name, artifact.path, artifact_type, description, metadata)
        self._save_run(run)
        return True
    
    def search_runs(self, query: str, experiment_id: Optional[str] = None) -> List[ExperimentRun]:
        """Search runs by query."""
        runs = self.list_runs(experiment_id)
        
        matching_runs = []
        query_lower = query.lower()
        
        for run in runs:
            # Search in run name, notes, tags
            if (query_lower in run.name.lower() or
                query_lower in run.notes.lower() or
                any(query_lower in str(v).lower() for v in run.tags.values())):
                matching_runs.append(run)
                continue
            
            # Search in parameters
            for param in run.parameters.values():
                if (query_lower in param.name.lower() or
                    query_lower in str(param.value).lower()):
                    matching_runs.append(run)
                    break
        
        return matching_runs
    
    def get_run_metrics_summary(self, run_id: str) -> Dict[str, Any]:
        """Get metrics summary for a run."""
        if run_id not in self.runs:
            return {}
        
        run = self.runs[run_id]
        summary = {}
        
        for metric_name, metric_list in run.metrics.items():
            if not metric_list:
                continue
            
            values = [m.value for m in metric_list if isinstance(m.value, (int, float))]
            if values:
                summary[metric_name] = {
                    'latest': metric_list[-1].value,
                    'count': len(metric_list),
                    'min': min(values),
                    'max': max(values),
                    'avg': sum(values) / len(values),
                    'steps': [m.step for m in metric_list]
                }
            else:
                summary[metric_name] = {
                    'latest': metric_list[-1].value,
                    'count': len(metric_list),
                    'steps': [m.step for m in metric_list]
                }
        
        return summary
    
    def get_experiment_summary(self, experiment_id: str) -> Dict[str, Any]:
        """Get experiment summary."""
        if experiment_id not in self.experiments:
            return {}
        
        experiment = self.experiments[experiment_id]
        runs = self.list_runs(experiment_id)
        
        total_runs = len(runs)
        completed_runs = sum(1 for run in runs if run.status == RunStatus.COMPLETED)
        failed_runs = sum(1 for run in runs if run.status == RunStatus.FAILED)
        active_runs = sum(1 for run in runs if run.is_active)
        
        return {
            'experiment': experiment.to_dict(),
            'run_counts': {
                'total': total_runs,
                'completed': completed_runs,
                'failed': failed_runs,
                'active': active_runs,
                'success_rate': completed_runs / total_runs if total_runs > 0 else 0
            },
            'latest_runs': [run.to_dict() for run in runs[:5]],  # Latest 5 runs
            'common_metrics': self._get_common_metrics(runs),
            'common_parameters': self._get_common_parameters(runs)
        }
    
    def _get_common_metrics(self, runs: List[ExperimentRun]) -> List[str]:
        """Get metrics that appear in multiple runs."""
        metric_counts = {}
        for run in runs:
            for metric_name in run.metrics.keys():
                metric_counts[metric_name] = metric_counts.get(metric_name, 0) + 1
        
        # Return metrics that appear in at least half the runs
        threshold = max(1, len(runs) // 2)
        return [name for name, count in metric_counts.items() if count >= threshold]
    
    def _get_common_parameters(self, runs: List[ExperimentRun]) -> List[str]:
        """Get parameters that appear in multiple runs."""
        param_counts = {}
        for run in runs:
            for param_name in run.parameters.keys():
                param_counts[param_name] = param_counts.get(param_name, 0) + 1
        
        # Return parameters that appear in at least half the runs
        threshold = max(1, len(runs) // 2)
        return [name for name, count in param_counts.items() if count >= threshold]


# Convenience functions
def create_experiment_tracker(storage_path: str = "./experiments") -> ExperimentTracker:
    """Create an experiment tracker instance."""
    return ExperimentTracker(storage_path)


def create_experiment(tracker: ExperimentTracker, name: str, description: str = "",
                     tags: Optional[Dict[str, str]] = None, created_by: str = "") -> Experiment:
    """Create a new experiment."""
    return tracker.create_experiment(name, description, tags, "", created_by)


def create_run(tracker: ExperimentTracker, experiment_id: str, name: str = "",
              tags: Optional[Dict[str, str]] = None, created_by: str = "") -> Optional[ExperimentRun]:
    """Create a new run."""
    return tracker.create_run(experiment_id, name, tags, "", "", created_by)


# Export all classes and functions
__all__ = [
    'ExperimentStatus', 'RunStatus', 'ArtifactType', 'MetricType',
    'Parameter', 'Metric', 'Artifact', 'ExperimentRun', 'Experiment',
    'ExperimentComparator', 'ArtifactManager', 'ExperimentTracker',
    'create_experiment_tracker', 'create_experiment', 'create_run'
]