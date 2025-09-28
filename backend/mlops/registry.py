"""
Module 62: MLOps Model Registry Service

This module provides comprehensive model registry functionality for managing,
versioning, and tracking machine learning models in the algotrading platform.
Includes model metadata management, versioning, lifecycle tracking, and artifact storage.
"""

import asyncio
import json
import hashlib
import shutil
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """Model lifecycle status."""
    DRAFT = "draft"
    REGISTERED = "registered"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"


class ModelStage(Enum):
    """Model deployment stage."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    CHAMPION = "champion"
    CHALLENGER = "challenger"


class ArtifactType(Enum):
    """Model artifact types."""
    MODEL = "model"
    PREPROCESSOR = "preprocessor"
    POSTPROCESSOR = "postprocessor"
    METRICS = "metrics"
    LOGS = "logs"
    CONFIG = "config"
    DOCUMENTATION = "documentation"


@dataclass
class ModelArtifact:
    """Model artifact metadata."""
    artifact_id: str
    name: str
    type: ArtifactType
    file_path: str
    size_bytes: int
    checksum: str
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelVersion:
    """Model version metadata."""
    model_name: str
    version: str
    stage: ModelStage
    status: ModelStatus
    description: str
    created_by: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    artifacts: List[ModelArtifact] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)
    lineage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Model information summary."""
    name: str
    description: str
    owner: str
    created_at: datetime
    updated_at: datetime
    latest_version: Optional[str] = None
    versions: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)


class ModelRegistryStorage:
    """Backend storage for model registry."""
    
    def __init__(self, storage_path: str = "models/registry"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Storage structure
        self.models_path = self.storage_path / "models"
        self.metadata_path = self.storage_path / "metadata"
        self.artifacts_path = self.storage_path / "artifacts"
        
        for path in [self.models_path, self.metadata_path, self.artifacts_path]:
            path.mkdir(parents=True, exist_ok=True)
    
    def _get_model_path(self, model_name: str) -> Path:
        """Get model storage path."""
        return self.models_path / model_name
    
    def _get_metadata_file(self, model_name: str) -> Path:
        """Get model metadata file path."""
        return self.metadata_path / f"{model_name}.json"
    
    def _get_version_metadata_file(self, model_name: str, version: str) -> Path:
        """Get version metadata file path."""
        return self.metadata_path / f"{model_name}_v{version}.json"
    
    def _get_artifact_path(self, model_name: str, version: str, artifact_name: str) -> Path:
        """Get artifact storage path."""
        return self.artifacts_path / model_name / version / artifact_name
    
    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate file checksum."""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating checksum for {file_path}: {e}")
            return ""
    
    def save_model_info(self, model_info: ModelInfo) -> bool:
        """Save model information."""
        try:
            metadata_file = self._get_metadata_file(model_info.name)
            with open(metadata_file, 'w') as f:
                data = {
                    'name': model_info.name,
                    'description': model_info.description,
                    'owner': model_info.owner,
                    'created_at': model_info.created_at.isoformat(),
                    'updated_at': model_info.updated_at.isoformat(),
                    'latest_version': model_info.latest_version,
                    'versions': model_info.versions,
                    'tags': model_info.tags
                }
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving model info: {e}")
            return False
    
    def load_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Load model information."""
        try:
            metadata_file = self._get_metadata_file(model_name)
            if not metadata_file.exists():
                return None
            
            with open(metadata_file, 'r') as f:
                data = json.load(f)
            
            return ModelInfo(
                name=data['name'],
                description=data['description'],
                owner=data['owner'],
                created_at=datetime.fromisoformat(data['created_at']),
                updated_at=datetime.fromisoformat(data['updated_at']),
                latest_version=data.get('latest_version'),
                versions=data.get('versions', []),
                tags=data.get('tags', {})
            )
        except Exception as e:
            logger.error(f"Error loading model info: {e}")
            return None
    
    def save_model_version(self, model_version: ModelVersion) -> bool:
        """Save model version."""
        try:
            version_file = self._get_version_metadata_file(
                model_version.model_name, model_version.version
            )
            
            # Convert artifacts to serializable format
            artifacts_data = []
            for artifact in model_version.artifacts:
                artifacts_data.append({
                    'artifact_id': artifact.artifact_id,
                    'name': artifact.name,
                    'type': artifact.type.value,
                    'file_path': artifact.file_path,
                    'size_bytes': artifact.size_bytes,
                    'checksum': artifact.checksum,
                    'created_at': artifact.created_at.isoformat(),
                    'metadata': artifact.metadata
                })
            
            data = {
                'model_name': model_version.model_name,
                'version': model_version.version,
                'stage': model_version.stage.value,
                'status': model_version.status.value,
                'description': model_version.description,
                'created_by': model_version.created_by,
                'created_at': model_version.created_at.isoformat(),
                'updated_at': model_version.updated_at.isoformat(),
                'artifacts': artifacts_data,
                'metrics': model_version.metrics,
                'parameters': model_version.parameters,
                'tags': model_version.tags,
                'lineage': model_version.lineage
            }
            
            with open(version_file, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving model version: {e}")
            return False
    
    def load_model_version(self, model_name: str, version: str) -> Optional[ModelVersion]:
        """Load model version."""
        try:
            version_file = self._get_version_metadata_file(model_name, version)
            if not version_file.exists():
                return None
            
            with open(version_file, 'r') as f:
                data = json.load(f)
            
            # Convert artifacts back to objects
            artifacts = []
            for artifact_data in data.get('artifacts', []):
                artifact = ModelArtifact(
                    artifact_id=artifact_data['artifact_id'],
                    name=artifact_data['name'],
                    type=ArtifactType(artifact_data['type']),
                    file_path=artifact_data['file_path'],
                    size_bytes=artifact_data['size_bytes'],
                    checksum=artifact_data['checksum'],
                    created_at=datetime.fromisoformat(artifact_data['created_at']),
                    metadata=artifact_data.get('metadata', {})
                )
                artifacts.append(artifact)
            
            return ModelVersion(
                model_name=data['model_name'],
                version=data['version'],
                stage=ModelStage(data['stage']),
                status=ModelStatus(data['status']),
                description=data['description'],
                created_by=data['created_by'],
                created_at=datetime.fromisoformat(data['created_at']),
                updated_at=datetime.fromisoformat(data['updated_at']),
                artifacts=artifacts,
                metrics=data.get('metrics', {}),
                parameters=data.get('parameters', {}),
                tags=data.get('tags', {}),
                lineage=data.get('lineage', {})
            )
        except Exception as e:
            logger.error(f"Error loading model version: {e}")
            return None
    
    def store_artifact(self, model_name: str, version: str, 
                      artifact_name: str, source_path: str) -> Optional[ModelArtifact]:
        """Store model artifact."""
        try:
            # Create artifact storage path
            artifact_path = self._get_artifact_path(model_name, version, artifact_name)
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy artifact file
            shutil.copy2(source_path, artifact_path)
            
            # Calculate metadata
            size_bytes = artifact_path.stat().st_size
            checksum = self._calculate_checksum(str(artifact_path))
            
            # Determine artifact type based on file extension
            file_ext = Path(source_path).suffix.lower()
            artifact_type = ArtifactType.MODEL  # Default
            if file_ext in ['.pkl', '.joblib', '.h5', '.pb']:
                artifact_type = ArtifactType.MODEL
            elif file_ext in ['.json', '.yaml', '.yml']:
                artifact_type = ArtifactType.CONFIG
            elif file_ext in ['.log', '.txt']:
                artifact_type = ArtifactType.LOGS
            elif file_ext in ['.md', '.pdf', '.html']:
                artifact_type = ArtifactType.DOCUMENTATION
            
            return ModelArtifact(
                artifact_id=f"{model_name}_{version}_{artifact_name}",
                name=artifact_name,
                type=artifact_type,
                file_path=str(artifact_path),
                size_bytes=size_bytes,
                checksum=checksum,
                metadata={'original_path': source_path}
            )
        except Exception as e:
            logger.error(f"Error storing artifact: {e}")
            return None
    
    def list_models(self) -> List[str]:
        """List all registered models."""
        try:
            models = []
            for metadata_file in self.metadata_path.glob("*.json"):
                if "_v" not in metadata_file.stem:  # Skip version files
                    models.append(metadata_file.stem)
            return sorted(models)
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []
    
    def list_versions(self, model_name: str) -> List[str]:
        """List all versions for a model."""
        try:
            versions = []
            pattern = f"{model_name}_v*.json"
            for version_file in self.metadata_path.glob(pattern):
                version = version_file.stem.split("_v")[1]
                versions.append(version)
            return sorted(versions, reverse=True)  # Latest first
        except Exception as e:
            logger.error(f"Error listing versions: {e}")
            return []


class ModelValidator:
    """Model validation service."""
    
    def __init__(self):
        self.validation_rules = {}
    
    def add_validation_rule(self, name: str, rule_func):
        """Add custom validation rule."""
        self.validation_rules[name] = rule_func
    
    def validate_model_name(self, name: str) -> Tuple[bool, str]:
        """Validate model name."""
        if not name:
            return False, "Model name cannot be empty"
        
        if not name.replace("_", "").replace("-", "").isalnum():
            return False, "Model name can only contain alphanumeric characters, hyphens, and underscores"
        
        if len(name) > 100:
            return False, "Model name cannot exceed 100 characters"
        
        return True, ""
    
    def validate_version(self, version: str) -> Tuple[bool, str]:
        """Validate model version."""
        if not version:
            return False, "Version cannot be empty"
        
        # Basic semver pattern
        import re
        pattern = r'^v?\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$'
        if not re.match(pattern, version):
            return False, "Version must follow semantic versioning (e.g., v1.0.0)"
        
        return True, ""
    
    def validate_model_version(self, model_version: ModelVersion) -> Tuple[bool, List[str]]:
        """Validate complete model version."""
        errors = []
        
        # Validate name
        name_valid, name_error = self.validate_model_name(model_version.model_name)
        if not name_valid:
            errors.append(f"Model name: {name_error}")
        
        # Validate version
        version_valid, version_error = self.validate_version(model_version.version)
        if not version_valid:
            errors.append(f"Version: {version_error}")
        
        # Validate description
        if not model_version.description:
            errors.append("Description is required")
        elif len(model_version.description) > 1000:
            errors.append("Description cannot exceed 1000 characters")
        
        # Validate created_by
        if not model_version.created_by:
            errors.append("Created by field is required")
        
        # Apply custom validation rules
        for rule_name, rule_func in self.validation_rules.items():
            try:
                is_valid, error_msg = rule_func(model_version)
                if not is_valid:
                    errors.append(f"{rule_name}: {error_msg}")
            except Exception as e:
                logger.error(f"Error in validation rule {rule_name}: {e}")
                errors.append(f"Validation rule {rule_name} failed")
        
        return len(errors) == 0, errors


class ModelLifecycleManager:
    """Manages model lifecycle transitions."""
    
    def __init__(self):
        self.transition_rules = {
            ModelStatus.DRAFT: [ModelStatus.REGISTERED, ModelStatus.ARCHIVED],
            ModelStatus.REGISTERED: [ModelStatus.STAGING, ModelStatus.ARCHIVED],
            ModelStatus.STAGING: [ModelStatus.PRODUCTION, ModelStatus.REGISTERED, ModelStatus.ARCHIVED],
            ModelStatus.PRODUCTION: [ModelStatus.DEPRECATED, ModelStatus.ARCHIVED],
            ModelStatus.DEPRECATED: [ModelStatus.ARCHIVED],
            ModelStatus.ARCHIVED: []  # No transitions from archived
        }
    
    def can_transition(self, from_status: ModelStatus, to_status: ModelStatus) -> bool:
        """Check if status transition is allowed."""
        return to_status in self.transition_rules.get(from_status, [])
    
    def get_allowed_transitions(self, current_status: ModelStatus) -> List[ModelStatus]:
        """Get allowed transitions from current status."""
        return self.transition_rules.get(current_status, [])
    
    def transition_status(self, model_version: ModelVersion, 
                         new_status: ModelStatus) -> Tuple[bool, str]:
        """Transition model status."""
        if not self.can_transition(model_version.status, new_status):
            return False, f"Cannot transition from {model_version.status.value} to {new_status.value}"
        
        old_status = model_version.status
        model_version.status = new_status
        model_version.updated_at = datetime.now()
        
        logger.info(f"Model {model_version.model_name} v{model_version.version} "
                   f"transitioned from {old_status.value} to {new_status.value}")
        
        return True, ""


class ModelRegistry:
    """Main model registry service."""
    
    def __init__(self, storage_path: str = "models/registry"):
        self.storage = ModelRegistryStorage(storage_path)
        self.validator = ModelValidator()
        self.lifecycle_manager = ModelLifecycleManager()
        self.metrics = {
            'models_registered': 0,
            'versions_created': 0,
            'artifacts_stored': 0,
            'queries_executed': 0
        }
    
    async def register_model(self, name: str, description: str, 
                           owner: str, tags: Optional[Dict[str, str]] = None) -> ModelInfo:
        """Register a new model."""
        try:
            # Validate model name
            name_valid, name_error = self.validator.validate_model_name(name)
            if not name_valid:
                raise ValueError(f"Invalid model name: {name_error}")
            
            # Check if model already exists
            existing_model = self.storage.load_model_info(name)
            if existing_model:
                raise ValueError(f"Model '{name}' already exists")
            
            # Create model info
            model_info = ModelInfo(
                name=name,
                description=description,
                owner=owner,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                tags=tags or {}
            )
            
            # Save to storage
            if not self.storage.save_model_info(model_info):
                raise RuntimeError("Failed to save model info")
            
            self.metrics['models_registered'] += 1
            logger.info(f"Model '{name}' registered successfully")
            return model_info
            
        except Exception as e:
            logger.error(f"Error registering model: {e}")
            raise
    
    async def create_model_version(self, model_name: str, version: str,
                                 description: str, created_by: str,
                                 stage: ModelStage = ModelStage.DEVELOPMENT,
                                 metrics: Optional[Dict[str, float]] = None,
                                 parameters: Optional[Dict[str, Any]] = None,
                                 tags: Optional[Dict[str, str]] = None) -> ModelVersion:
        """Create a new model version."""
        try:
            # Check if model exists
            model_info = self.storage.load_model_info(model_name)
            if not model_info:
                raise ValueError(f"Model '{model_name}' not found")
            
            # Check if version already exists
            existing_version = self.storage.load_model_version(model_name, version)
            if existing_version:
                raise ValueError(f"Version '{version}' already exists for model '{model_name}'")
            
            # Create model version
            model_version = ModelVersion(
                model_name=model_name,
                version=version,
                stage=stage,
                status=ModelStatus.DRAFT,
                description=description,
                created_by=created_by,
                metrics=metrics or {},
                parameters=parameters or {},
                tags=tags or {}
            )
            
            # Validate model version
            is_valid, errors = self.validator.validate_model_version(model_version)
            if not is_valid:
                raise ValueError(f"Validation failed: {'; '.join(errors)}")
            
            # Save version
            if not self.storage.save_model_version(model_version):
                raise RuntimeError("Failed to save model version")
            
            # Update model info
            model_info.latest_version = version
            if version not in model_info.versions:
                model_info.versions.append(version)
            model_info.updated_at = datetime.now()
            self.storage.save_model_info(model_info)
            
            self.metrics['versions_created'] += 1
            logger.info(f"Version '{version}' created for model '{model_name}'")
            return model_version
            
        except Exception as e:
            logger.error(f"Error creating model version: {e}")
            raise
    
    async def add_artifact(self, model_name: str, version: str,
                          artifact_name: str, source_path: str,
                          artifact_type: Optional[ArtifactType] = None,
                          metadata: Optional[Dict[str, Any]] = None) -> ModelArtifact:
        """Add artifact to model version."""
        try:
            # Load model version
            model_version = self.storage.load_model_version(model_name, version)
            if not model_version:
                raise ValueError(f"Model version '{model_name}' v'{version}' not found")
            
            # Store artifact
            artifact = self.storage.store_artifact(
                model_name, version, artifact_name, source_path
            )
            if not artifact:
                raise RuntimeError("Failed to store artifact")
            
            # Override type if provided
            if artifact_type:
                artifact.type = artifact_type
            
            # Add metadata
            if metadata:
                artifact.metadata.update(metadata)
            
            # Add to model version
            model_version.artifacts.append(artifact)
            model_version.updated_at = datetime.now()
            
            # Save updated version
            if not self.storage.save_model_version(model_version):
                raise RuntimeError("Failed to update model version")
            
            self.metrics['artifacts_stored'] += 1
            logger.info(f"Artifact '{artifact_name}' added to {model_name} v{version}")
            return artifact
            
        except Exception as e:
            logger.error(f"Error adding artifact: {e}")
            raise
    
    async def transition_model_status(self, model_name: str, version: str,
                                    new_status: ModelStatus) -> bool:
        """Transition model version status."""
        try:
            # Load model version
            model_version = self.storage.load_model_version(model_name, version)
            if not model_version:
                raise ValueError(f"Model version '{model_name}' v'{version}' not found")
            
            # Perform transition
            success, error = self.lifecycle_manager.transition_status(model_version, new_status)
            if not success:
                raise ValueError(error)
            
            # Save updated version
            if not self.storage.save_model_version(model_version):
                raise RuntimeError("Failed to save status transition")
            
            return True
            
        except Exception as e:
            logger.error(f"Error transitioning status: {e}")
            raise
    
    async def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Get model information."""
        self.metrics['queries_executed'] += 1
        return self.storage.load_model_info(model_name)
    
    async def get_model_version(self, model_name: str, version: str) -> Optional[ModelVersion]:
        """Get specific model version."""
        self.metrics['queries_executed'] += 1
        return self.storage.load_model_version(model_name, version)
    
    async def list_models(self) -> List[ModelInfo]:
        """List all registered models."""
        self.metrics['queries_executed'] += 1
        models = []
        for model_name in self.storage.list_models():
            model_info = self.storage.load_model_info(model_name)
            if model_info:
                models.append(model_info)
        return models
    
    async def list_model_versions(self, model_name: str) -> List[ModelVersion]:
        """List all versions of a model."""
        self.metrics['queries_executed'] += 1
        versions = []
        for version in self.storage.list_versions(model_name):
            model_version = self.storage.load_model_version(model_name, version)
            if model_version:
                versions.append(model_version)
        return versions
    
    async def search_models(self, query: str, tags: Optional[Dict[str, str]] = None) -> List[ModelInfo]:
        """Search models by name, description, or tags."""
        self.metrics['queries_executed'] += 1
        all_models = await self.list_models()
        matching_models = []
        
        for model in all_models:
            matches = False
            
            # Check name and description if query provided
            if query:
                if (query.lower() in model.name.lower() or 
                    query.lower() in model.description.lower()):
                    matches = True
            
            # Check tags if provided
            if tags:
                matches_tags = all(
                    model.tags.get(key) == value 
                    for key, value in tags.items()
                )
                if matches_tags:
                    matches = True
            
            # If no query and no tags, match all (shouldn't happen in practice)
            if not query and not tags:
                matches = True
            
            if matches:
                matching_models.append(model)
        
        return matching_models
    
    async def get_registry_metrics(self) -> Dict[str, Any]:
        """Get registry metrics."""
        return {
            **self.metrics,
            'total_models': len(self.storage.list_models()),
            'storage_path': str(self.storage.storage_path)
        }
    
    async def cleanup_old_versions(self, model_name: str, keep_latest: int = 5) -> int:
        """Clean up old model versions."""
        try:
            versions = self.storage.list_versions(model_name)
            if len(versions) <= keep_latest:
                return 0
            
            versions_to_remove = versions[keep_latest:]
            removed_count = 0
            
            for version in versions_to_remove:
                model_version = self.storage.load_model_version(model_name, version)
                if model_version and model_version.status == ModelStatus.ARCHIVED:
                    # Remove version metadata file
                    version_file = self.storage._get_version_metadata_file(model_name, version)
                    if version_file.exists():
                        version_file.unlink()
                        removed_count += 1
                        logger.info(f"Removed old version {model_name} v{version}")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error cleaning up versions: {e}")
            return 0


# Convenience functions
async def register_model(name: str, description: str, owner: str, 
                        registry: Optional[ModelRegistry] = None) -> ModelInfo:
    """Convenience function to register a model."""
    if registry is None:
        registry = ModelRegistry()
    return await registry.register_model(name, description, owner)


async def create_version(model_name: str, version: str, description: str, 
                        created_by: str, registry: Optional[ModelRegistry] = None) -> ModelVersion:
    """Convenience function to create a model version."""
    if registry is None:
        registry = ModelRegistry()
    return await registry.create_model_version(model_name, version, description, created_by)


def get_model_registry(storage_path: str = "models/registry") -> ModelRegistry:
    """Get a model registry instance."""
    return ModelRegistry(storage_path)


# Module exports
__all__ = [
    'ModelStatus', 'ModelStage', 'ArtifactType',
    'ModelArtifact', 'ModelVersion', 'ModelInfo',
    'ModelRegistryStorage', 'ModelValidator', 'ModelLifecycleManager',
    'ModelRegistry',
    'register_model', 'create_version', 'get_model_registry'
]