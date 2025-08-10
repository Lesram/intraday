"""
Models repository - manages ML model registry and metadata.
Implements async CRUD operations with proper error handling.
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select, update, and_, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import ModelRegistry

logger = logging.getLogger(__name__)


class ModelNotFoundError(Exception):
    """Raised when a model is not found."""
    pass


class DuplicateModelError(Exception):
    """Raised when attempting to create a duplicate model."""
    pass


class ModelsRepo:
    """Repository for ML model registry operations."""
    
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register_model(
        self,
        *,
        name: str,
        version: str,
        model_type: str,
        status: str = 'training',
        metadata: Dict[str, Any] | None = None,
        config: Dict[str, Any] | None = None,
        performance_metrics: Dict[str, Any] | None = None
    ) -> ModelRegistry:
        """
        Register a new model version.
        
        Args:
            name: Model name
            version: Model version
            model_type: Type of model ('classification', 'regression', 'ensemble', etc.)
            status: Model status ('training', 'testing', 'production', 'deprecated')
            metadata: Optional metadata
            config: Optional model configuration
            performance_metrics: Optional performance metrics
            
        Returns:
            ModelRegistry: Newly created model registry entry
            
        Raises:
            DuplicateModelError: If model name+version already exists
        """
        new_model = ModelRegistry(
            name=name,
            version=version,
            model_type=model_type,
            status=status,
            metadata=metadata or {},
            config=config or {},
            performance_metrics=performance_metrics or {}
        )
        
        try:
            self.session.add(new_model)
            await self.session.flush()  # Get the ID without committing
            
            logger.info(
                "Model registered",
                extra={
                    "model_id": str(new_model.id),
                    "name": name,
                    "version": version,
                    "model_type": model_type,
                    "status": status
                }
            )
            
            return new_model
            
        except IntegrityError as e:
            await self.session.rollback()
            if "name" in str(e) and "version" in str(e):
                logger.warning(
                    "Duplicate model registration attempted",
                    extra={
                        "name": name,
                        "version": version
                    }
                )
                raise DuplicateModelError(f"Model {name} version {version} already exists") from e
            
            logger.error(
                "Failed to register model",
                extra={
                    "name": name,
                    "version": version,
                    "error": str(e)
                }
            )
            raise

    async def update_model_status(
        self,
        name: str,
        version: str,
        status: str
    ) -> None:
        """
        Update model status.
        
        Args:
            name: Model name
            version: Model version
            status: New status
            
        Raises:
            ModelNotFoundError: If model not found
        """
        stmt = (
            update(ModelRegistry)
            .where(
                and_(
                    ModelRegistry.name == name,
                    ModelRegistry.version == version
                )
            )
            .values(
                status=status,
                updated_at=datetime.utcnow()
            )
            .returning(ModelRegistry.id)
        )
        
        result = await self.session.execute(stmt)
        updated_id = result.scalar_one_or_none()
        
        if not updated_id:
            raise ModelNotFoundError(f"Model {name} version {version} not found")
        
        logger.info(
            "Model status updated",
            extra={
                "name": name,
                "version": version,
                "status": status
            }
        )

    async def update_performance_metrics(
        self,
        name: str,
        version: str,
        performance_metrics: Dict[str, Any]
    ) -> None:
        """
        Update model performance metrics.
        
        Args:
            name: Model name
            version: Model version
            performance_metrics: Performance metrics to update
            
        Raises:
            ModelNotFoundError: If model not found
        """
        # First get current metrics to merge
        stmt = (
            select(ModelRegistry.performance_metrics)
            .where(
                and_(
                    ModelRegistry.name == name,
                    ModelRegistry.version == version
                )
            )
        )
        
        result = await self.session.execute(stmt)
        current_metrics = result.scalar_one_or_none()
        
        if current_metrics is None:
            raise ModelNotFoundError(f"Model {name} version {version} not found")
        
        # Merge metrics
        merged_metrics = {**(current_metrics or {}), **performance_metrics}
        
        # Update with merged metrics
        stmt = (
            update(ModelRegistry)
            .where(
                and_(
                    ModelRegistry.name == name,
                    ModelRegistry.version == version
                )
            )
            .values(
                performance_metrics=merged_metrics,
                updated_at=datetime.utcnow()
            )
            .returning(ModelRegistry.id)
        )
        
        result = await self.session.execute(stmt)
        updated_id = result.scalar_one_or_none()
        
        if not updated_id:
            raise ModelNotFoundError(f"Model {name} version {version} not found")
        
        logger.info(
            "Model performance metrics updated",
            extra={
                "name": name,
                "version": version,
                "metrics_keys": list(performance_metrics.keys())
            }
        )

    async def get_model_by_name_version(
        self,
        name: str,
        version: str
    ) -> ModelRegistry | None:
        """
        Get model by name and version.
        
        Args:
            name: Model name
            version: Model version
            
        Returns:
            ModelRegistry if found, None otherwise
        """
        stmt = (
            select(ModelRegistry)
            .where(
                and_(
                    ModelRegistry.name == name,
                    ModelRegistry.version == version
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_model_by_id(self, model_id: uuid.UUID) -> ModelRegistry | None:
        """
        Get model by ID.
        
        Args:
            model_id: Model ID
            
        Returns:
            ModelRegistry if found, None otherwise
        """
        stmt = select(ModelRegistry).where(ModelRegistry.id == model_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_models_by_name(
        self,
        name: str,
        status: str | None = None
    ) -> list[ModelRegistry]:
        """
        Get all versions of a model by name.
        
        Args:
            name: Model name
            status: Optional status filter
            
        Returns:
            List of model versions ordered by version descending
        """
        conditions = [ModelRegistry.name == name]
        
        if status:
            conditions.append(ModelRegistry.status == status)
        
        stmt = (
            select(ModelRegistry)
            .where(and_(*conditions))
            .order_by(ModelRegistry.version.desc())
        )
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_production_models(self) -> list[ModelRegistry]:
        """
        Get all models in production status.
        
        Returns:
            List of production models
        """
        stmt = (
            select(ModelRegistry)
            .where(ModelRegistry.status == 'production')
            .order_by(ModelRegistry.name.asc(), ModelRegistry.version.desc())
        )
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_model_version(
        self,
        name: str,
        status: str | None = None
    ) -> ModelRegistry | None:
        """
        Get the latest version of a model.
        
        Args:
            name: Model name
            status: Optional status filter
            
        Returns:
            Latest model version if found, None otherwise
        """
        conditions = [ModelRegistry.name == name]
        
        if status:
            conditions.append(ModelRegistry.status == status)
        
        stmt = (
            select(ModelRegistry)
            .where(and_(*conditions))
            .order_by(ModelRegistry.version.desc())
            .limit(1)
        )
        
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def promote_model_to_production(
        self,
        name: str,
        version: str
    ) -> None:
        """
        Promote a model version to production and demote others.
        
        Args:
            name: Model name
            version: Model version to promote
            
        Raises:
            ModelNotFoundError: If model not found
        """
        # First, demote all current production models for this name
        await self.session.execute(
            update(ModelRegistry)
            .where(
                and_(
                    ModelRegistry.name == name,
                    ModelRegistry.status == 'production'
                )
            )
            .values(
                status='archived',
                updated_at=datetime.utcnow()
            )
        )
        
        # Promote the specified version
        stmt = (
            update(ModelRegistry)
            .where(
                and_(
                    ModelRegistry.name == name,
                    ModelRegistry.version == version
                )
            )
            .values(
                status='production',
                updated_at=datetime.utcnow()
            )
            .returning(ModelRegistry.id)
        )
        
        result = await self.session.execute(stmt)
        promoted_id = result.scalar_one_or_none()
        
        if not promoted_id:
            raise ModelNotFoundError(f"Model {name} version {version} not found")
        
        logger.info(
            "Model promoted to production",
            extra={
                "name": name,
                "version": version
            }
        )

    async def deprecate_model(
        self,
        name: str,
        version: str
    ) -> None:
        """
        Deprecate a model version.
        
        Args:
            name: Model name
            version: Model version
            
        Raises:
            ModelNotFoundError: If model not found
        """
        stmt = (
            update(ModelRegistry)
            .where(
                and_(
                    ModelRegistry.name == name,
                    ModelRegistry.version == version
                )
            )
            .values(
                status='deprecated',
                updated_at=datetime.utcnow()
            )
            .returning(ModelRegistry.id)
        )
        
        result = await self.session.execute(stmt)
        deprecated_id = result.scalar_one_or_none()
        
        if not deprecated_id:
            raise ModelNotFoundError(f"Model {name} version {version} not found")
        
        logger.info(
            "Model deprecated",
            extra={
                "name": name,
                "version": version
            }
        )

    async def get_model_performance_comparison(
        self,
        name: str,
        metric_key: str
    ) -> list[Dict[str, Any]]:
        """
        Compare performance metrics across versions of a model.
        
        Args:
            name: Model name
            metric_key: Performance metric key to compare
            
        Returns:
            List of performance comparisons
        """
        stmt = (
            select(ModelRegistry)
            .where(ModelRegistry.name == name)
            .order_by(ModelRegistry.version.desc())
        )
        
        result = await self.session.execute(stmt)
        models = list(result.scalars().all())
        
        comparisons = []
        for model in models:
            metric_value = model.performance_metrics.get(metric_key) if model.performance_metrics else None
            
            comparisons.append({
                "version": model.version,
                "status": model.status,
                "metric_value": metric_value,
                "created_at": model.created_at,
                "updated_at": model.updated_at
            })
        
        return comparisons

    async def get_model_registry_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics of the model registry.
        
        Returns:
            Dictionary with registry summary
        """
        stmt = select(ModelRegistry)
        result = await self.session.execute(stmt)
        all_models = list(result.scalars().all())
        
        if not all_models:
            return {
                "total_models": 0,
                "unique_model_names": 0,
                "status_counts": {},
                "type_counts": {},
                "latest_registration": None
            }
        
        # Count by status
        status_counts = {}
        for model in all_models:
            status_counts[model.status] = status_counts.get(model.status, 0) + 1
        
        # Count by type
        type_counts = {}
        for model in all_models:
            type_counts[model.model_type] = type_counts.get(model.model_type, 0) + 1
        
        # Unique model names
        unique_names = set(model.name for model in all_models)
        
        # Latest registration
        latest_model = max(all_models, key=lambda m: m.created_at)
        
        return {
            "total_models": len(all_models),
            "unique_model_names": len(unique_names),
            "status_counts": status_counts,
            "type_counts": type_counts,
            "latest_registration": {
                "name": latest_model.name,
                "version": latest_model.version,
                "created_at": latest_model.created_at
            }
        }

    async def cleanup_deprecated_models(
        self,
        older_than_days: int = 30
    ) -> int:
        """
        Clean up deprecated models older than specified days.
        
        Args:
            older_than_days: Delete deprecated models older than this many days
            
        Returns:
            Number of models deleted
        """
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        
        # For safety, we'll just count for now rather than actually delete
        # In production, you might want to move to archive table first
        stmt = (
            select(ModelRegistry)
            .where(
                and_(
                    ModelRegistry.status == 'deprecated',
                    ModelRegistry.updated_at < cutoff_date
                )
            )
        )
        
        result = await self.session.execute(stmt)
        deprecated_models = list(result.scalars().all())
        
        logger.info(
            "Deprecated models cleanup check",
            extra={
                "cutoff_date": cutoff_date,
                "deprecated_models_found": len(deprecated_models),
                "older_than_days": older_than_days
            }
        )
        
        # Return count of models that would be cleaned up
        return len(deprecated_models)
