"""
AI/ML Ensemble Modeling System
Combines LSTM, XGBoost, and RandomForest for comprehensive price prediction
"""

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

import numpy as np
import pandas as pd

# ML/AI imports with fallback handling
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers

    TENSORFLOW_AVAILABLE = True
except ImportError as e:
    logging.warning(f"TensorFlow not available: {e}")
    TENSORFLOW_AVAILABLE = False

try:
    import joblib
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler

    SKLEARN_AVAILABLE = True
    JOBLIB_AVAILABLE = True
except ImportError as e:
    logging.warning(f"scikit-learn or joblib not available: {e}")
    SKLEARN_AVAILABLE = False
    JOBLIB_AVAILABLE = False

try:
    import xgboost as xgb

    XGBOOST_AVAILABLE = True
except ImportError as e:
    logging.warning(f"XGBoost not available: {e}")
    XGBOOST_AVAILABLE = False

from ..config import get_settings
from ..utils.logger import audit_logger

# Import MLOps components with fallback for backward compatibility
try:
    from ..mlops import SchemaMismatchError, get_model_manager
    MLOPS_AVAILABLE = True

    # Try to import observability components
    try:
        from ..infra.logging import get_structured_logger
        from ..infra.metrics import get_metrics_registry
        mlops_logger = get_structured_logger("models.ensemble")
        mlops_metrics = get_metrics_registry()
    except ImportError:
        mlops_logger = logging.getLogger("models.ensemble")
        mlops_metrics = None

except ImportError as e:
    logging.warning(f"MLOps integration not available: {e}")
    MLOPS_AVAILABLE = False
    mlops_logger = None
    mlops_metrics = None

    # Create dummy exception class for consistent exception handling
    class SchemaMismatchError(Exception):
        def __init__(self, message):
            super().__init__(message)
            self.expected_schema = {}
            self.received_schema = {}

# Import feature pipeline components (Branch 2.9)
try:
    from ..features.alignment import align_features_target
    from ..features.types import FeatureFrame, FeatureSchema, SchemaValidationError
    from ..features.validators import guard_no_lookahead
    FEATURE_PIPELINE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Feature pipeline components not available: {e}")
    FEATURE_PIPELINE_AVAILABLE = False


@dataclass
class ModelPrediction:
    """Container for model predictions"""

    symbol: str
    timestamp: datetime
    predictions: dict[str, float]  # model_name -> prediction
    confidence_scores: dict[str, float]  # model_name -> confidence
    ensemble_prediction: float
    ensemble_confidence: float
    metadata: dict[str, Any]


@dataclass
class ModelPerformance:
    """Container for model performance metrics"""

    model_name: str
    mse: float
    mae: float
    sharpe_ratio: float
    accuracy: float
    last_updated: datetime


class LSTMModel:
    """LSTM Neural Network for time series prediction with enhanced training controls"""

    def __init__(self, sequence_length: int = 60, features: int = 1,
                 max_epochs: int = 50, early_stopping_patience: int = 10,
                 random_seed: int | None = 42):
        self.sequence_length = sequence_length
        self.features = features
        self.max_epochs = max_epochs
        self.early_stopping_patience = early_stopping_patience
        self.random_seed = random_seed
        self.model = None
        self.scaler = None
        self.is_trained = False
        self.training_history = None

        # Set random seeds for reproducibility
        if self.random_seed is not None:
            np.random.seed(self.random_seed)
            if TENSORFLOW_AVAILABLE:
                try:
                    import tensorflow as tf
                    tf.random.set_seed(self.random_seed)
                except ImportError:
                    logging.warning("TensorFlow not available for seed setting")

    def build_model(self) -> Any | None:
        """Build LSTM architecture"""
        if not TENSORFLOW_AVAILABLE:
            logging.warning("TensorFlow not available, LSTM model disabled")
            return None

        try:
            model = keras.Sequential(
                [
                    layers.LSTM(
                        50,
                        return_sequences=True,
                        input_shape=(self.sequence_length, self.features),
                    ),
                    layers.Dropout(0.2),
                    layers.LSTM(50, return_sequences=True),
                    layers.Dropout(0.2),
                    layers.LSTM(50, return_sequences=False),
                    layers.Dropout(0.2),
                    layers.Dense(25, activation="relu"),
                    layers.Dense(1, activation="linear"),
                ]
            )

            model.compile(optimizer="adam", loss="mean_squared_error", metrics=["mae"])

            return model
        except Exception as e:
            logging.error(f"Error building LSTM model: {e}")
            return None

    def prepare_sequences(self, data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Prepare sequences for LSTM training"""
        X, y = [], []
        for i in range(self.sequence_length, len(data)):
            X.append(data[i - self.sequence_length : i])
            y.append(data[i])
        return np.array(X), np.array(y)

    async def train(self, data: pd.DataFrame, target_column: str = "close") -> bool:
        """Train LSTM model"""
        if not TENSORFLOW_AVAILABLE or not SKLEARN_AVAILABLE:
            return False

        try:
            # Prepare data
            from sklearn.preprocessing import StandardScaler

            self.scaler = StandardScaler()
            scaled_data = self.scaler.fit_transform(data[[target_column]].values)

            # Create sequences
            X, y = self.prepare_sequences(scaled_data)
            if len(X) == 0:
                return False

            # Build and train model
            self.model = self.build_model()
            if self.model is None:
                return False

            # Training with validation split and enhanced callbacks
            split_idx = int(len(X) * 0.8)
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]

            # Enhanced callbacks for better training
            callbacks = [
                keras.callbacks.EarlyStopping(
                    patience=self.early_stopping_patience,
                    restore_best_weights=True,
                    monitor='val_loss',
                    min_delta=0.001
                ),
                keras.callbacks.ReduceLROnPlateau(
                    monitor='val_loss',
                    factor=0.5,
                    patience=5,
                    min_lr=0.0001,
                    verbose=0
                )
            ]

            self.training_history = self.model.fit(
                X_train,
                y_train,
                validation_data=(X_val, y_val),
                epochs=self.max_epochs,
                batch_size=32,
                verbose=0,
                callbacks=callbacks,
            )

            self.is_trained = True
            return True

        except Exception as e:
            logging.error(f"Error training LSTM model: {e}")
            return False

    def predict(
        self, data: pd.DataFrame, target_column: str = "close"
    ) -> tuple[float, float]:
        """Make prediction with confidence score"""
        if not self.is_trained or self.model is None or self.scaler is None:
            return 0.0, 0.0

        try:
            # Scale recent data
            recent_data = data[[target_column]].tail(self.sequence_length).values
            scaled_recent = self.scaler.transform(recent_data)

            # Prepare input sequence
            X_pred = scaled_recent.reshape(1, self.sequence_length, 1)

            # Make prediction (predicting next period's scaled close price)
            prediction_scaled = self.model.predict(X_pred, verbose=0)[0][0]

            # Convert scaled prediction back to actual price
            # Note: We predict next price directly, then convert to return for strategy use
            prediction = self.scaler.inverse_transform([[prediction_scaled]])[0][0]

            # Calculate confidence (simple approach using model certainty)
            confidence = min(0.95, max(0.1, 1.0 - abs(prediction_scaled)))

            return float(prediction), float(confidence)

        except Exception as e:
            logging.error(f"Error in LSTM prediction: {e}")
            return 0.0, 0.0


class XGBoostModel:
    """XGBoost model for feature-based prediction"""

    def __init__(self):
        self.model = None
        self.scaler = None
        self.is_trained = False
        self.feature_importance = {}

    async def train(self, features: pd.DataFrame, target: pd.Series) -> bool:
        """Train XGBoost model"""
        if not XGBOOST_AVAILABLE or not SKLEARN_AVAILABLE:
            return False

        try:
            from sklearn.preprocessing import StandardScaler

            # Scale features
            self.scaler = StandardScaler()
            features_scaled = self.scaler.fit_transform(features)

            # Time series split for training
            tss = TimeSeriesSplit(n_splits=3)
            best_score = float("inf")

            for train_idx, val_idx in tss.split(features_scaled):
                X_train, X_val = features_scaled[train_idx], features_scaled[val_idx]
                y_train, y_val = target.iloc[train_idx], target.iloc[val_idx]

                model = xgb.XGBRegressor(
                    n_estimators=100,
                    max_depth=6,
                    learning_rate=0.1,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    random_state=42,
                )

                model.fit(
                    X_train,
                    y_train,
                    eval_set=[(X_val, y_val)],
                    early_stopping_rounds=10,
                    verbose=False,
                )

                # Evaluate
                val_pred = model.predict(X_val)
                score = mean_squared_error(y_val, val_pred)

                if score < best_score:
                    best_score = score
                    self.model = model

            # Store feature importance
            if self.model:
                self.feature_importance = dict(
                    zip(features.columns, self.model.feature_importances_, strict=False)
                )
                self.is_trained = True
                return True

        except Exception as e:
            logging.error(f"Error training XGBoost model: {e}")

        return False

    def predict(self, features: pd.DataFrame) -> tuple[float, float]:
        """Make prediction with confidence score"""
        if not self.is_trained or self.model is None or self.scaler is None:
            return 0.0, 0.0

        try:
            # Scale features
            features_scaled = self.scaler.transform(features)

            # Make prediction
            prediction = self.model.predict(features_scaled)[0]

            # Calculate confidence based on feature importance alignment
            confidence = 0.7  # Base confidence for XGBoost

            return float(prediction), float(confidence)

        except Exception as e:
            logging.error(f"Error in XGBoost prediction: {e}")
            return 0.0, 0.0


class RandomForestModel:
    """Random Forest model for ensemble diversity"""

    def __init__(self):
        self.model = None
        self.scaler = None
        self.is_trained = False

    async def train(self, features: pd.DataFrame, target: pd.Series) -> bool:
        """Train Random Forest model"""
        if not SKLEARN_AVAILABLE:
            return False

        try:
            from sklearn.preprocessing import StandardScaler

            # Scale features
            self.scaler = StandardScaler()
            features_scaled = self.scaler.fit_transform(features)

            # Train model
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            )

            self.model.fit(features_scaled, target)
            self.is_trained = True
            return True

        except Exception as e:
            logging.error(f"Error training Random Forest model: {e}")
            return False

    def predict(self, features: pd.DataFrame) -> tuple[float, float]:
        """Make prediction with confidence score"""
        if not self.is_trained or self.model is None or self.scaler is None:
            return 0.0, 0.0

        try:
            # Scale features
            features_scaled = self.scaler.transform(features)

            # Make prediction with uncertainty estimation
            predictions = []
            for estimator in self.model.estimators_:
                pred = estimator.predict(features_scaled)[0]
                predictions.append(pred)

            # Calculate mean and confidence from ensemble variance
            mean_pred = np.mean(predictions)
            variance = np.var(predictions)
            confidence = max(0.1, min(0.95, 1.0 - variance / (mean_pred**2 + 1e-8)))

            return float(mean_pred), float(confidence)

        except Exception as e:
            logging.error(f"Error in Random Forest prediction: {e}")
            return 0.0, 0.0


class EnsembleModel:
    """Main ensemble model combining LSTM, XGBoost, and Random Forest"""

    def __init__(self):
        self.models = {
            "lstm": LSTMModel(),
            "xgboost": XGBoostModel(),
            "random_forest": RandomForestModel(),
        }
        self.weights = {"lstm": 0.4, "xgboost": 0.4, "random_forest": 0.2}
        self.performance_history = []
        self.settings = get_settings()

        # MLOps integration
        self.mlops_enabled = MLOPS_AVAILABLE and getattr(self.settings, 'mlops', {}).get('inference_telemetry_enabled', True)
        if self.mlops_enabled:
            self.model_manager = get_model_manager()
        else:
            self.model_manager = None

    async def train_models(
        self,
        price_data: pd.DataFrame,
        features: pd.DataFrame,
        target_column: str = "close",
    ) -> dict[str, bool]:
        """Train all models in the ensemble"""
        results = {}

        # Train LSTM on price sequences
        results["lstm"] = await self.models["lstm"].train(price_data, target_column)

        # Train tree-based models on features with explicit index alignment
        target = price_data[target_column].shift(-1).dropna()  # Next period target

        # Ensure explicit alignment using shared index to prevent silent misalignment
        aligned_data = pd.concat([features, target.to_frame('target')], join='inner', axis=1).dropna()
        features_aligned = aligned_data.drop(columns=['target'])
        target_aligned = aligned_data['target']

        results["xgboost"] = await self.models["xgboost"].train(
            features_aligned, target_aligned
        )
        results["random_forest"] = await self.models["random_forest"].train(
            features_aligned, target_aligned
        )

        audit_logger.info(
            "ensemble_training_completed", results=results, timestamp=datetime.now()
        )

        return results

    def predict(
        self, price_data: pd.DataFrame, features: pd.DataFrame, symbol: str
    ) -> ModelPrediction:
        """Generate ensemble prediction with feature validation and MLOps integration"""
        start_time = datetime.now()
        predictions = {}
        confidences = {}

        # Branch 2.9: Feature validation and alignment
        if FEATURE_PIPELINE_AVAILABLE:
            try:
                # For inference: align features with current price but no target (y=None)
                price_series = price_data['close'] if 'close' in price_data.columns else price_data.iloc[:, -1]
                feature_frame = align_features_target(features, price_series)

                # Use validated features
                features = feature_frame.X

                # Run lookahead guard if enabled
                settings = get_settings()
                if getattr(settings.features, 'no_lookahead_enforced', True):
                    try:
                        guard_no_lookahead(features, price_series, list(features.columns))
                    except Exception as e:
                        if mlops_logger:
                            mlops_logger.warning("Lookahead detected during inference",
                                              extra={"symbol": symbol, "error": str(e)})
                        if mlops_metrics:
                            mlops_metrics.counter("feature_no_lookahead_violations_total",
                                               {"bucket": "inference"}).inc()

            except Exception as e:
                if mlops_logger:
                    mlops_logger.warning("Feature validation failed during inference",
                                      extra={"symbol": symbol, "error": str(e)})

        # MLOps: Check for schema mismatch and drift detection
        if self.mlops_enabled and self.model_manager:
            try:
                # Get champion model for this symbol
                champion = self.model_manager.registry.get_champion_model(symbol)
                if champion:
                    # Validate feature schema and reorder columns
                    _, _, metadata = self.model_manager.registry.load_artifacts(symbol, champion.version)

                    # Reorder columns by name for consistent schema
                    if 'feature_schema' in metadata:
                        expected_columns = metadata['feature_schema']['columns']
                        if set(features.columns) == set(expected_columns):
                            features = features[expected_columns]  # Reorder silently
                        else:
                            # Hard fail on missing/extra columns
                            missing = set(expected_columns) - set(features.columns)
                            extra = set(features.columns) - set(expected_columns)
                            if missing or extra:
                                raise SchemaValidationError(
                                    f"Schema mismatch for {symbol}",
                                    missing_columns=list(missing),
                                    extra_columns=list(extra)
                                )

                    features = self.model_manager.registry.assert_feature_schema(features, metadata)

                    # Check for data drift
                    drift_result = self.model_manager.drift_detector.detect_data_drift(symbol, features)
                    if drift_result and mlops_logger:
                        mlops_logger.warning(f"Data drift detected for {symbol}", {
                            "model": symbol,
                            "drift_type": drift_result.drift_type.value,
                            "severity": drift_result.severity,
                            "psi_score": drift_result.psi_score
                        })

            except (SchemaMismatchError, SchemaValidationError) as e:
                if mlops_logger:
                    mlops_logger.error(f"Schema validation failed for {symbol}", {
                        "error": str(e),
                        "missing_columns": getattr(e, 'missing_columns', []),
                        "extra_columns": getattr(e, 'extra_columns', [])
                    })
                if mlops_metrics:
                    mlops_metrics.counter("feature_schema_validations_total",
                                       {"result": "failed"}).inc()
                # Re-raise for API to return 400 error
                raise
            except Exception as e:
                if mlops_logger:
                    mlops_logger.warning(f"MLOps validation failed for {symbol}: {e}")

        # Get predictions from each model
        for model_name, model in self.models.items():
            try:
                if model_name == "lstm":
                    pred, conf = model.predict(price_data)
                else:
                    # Use latest features for tree models
                    latest_features = features.tail(1)
                    pred, conf = model.predict(latest_features)

                predictions[model_name] = pred
                confidences[model_name] = conf
            except Exception as e:
                # Log the error but continue with other models
                logging.warning(f"Model {model_name} failed during prediction: {e}")
                # Skip this model - don't include it in predictions
                continue

        # Calculate weighted ensemble prediction
        weighted_sum = sum(
            predictions[model] * self.weights[model] * confidences[model]
            for model in predictions
        )
        weight_sum = sum(
            self.weights[model] * confidences[model] for model in predictions
        )

        ensemble_prediction = weighted_sum / weight_sum if weight_sum > 0 else 0.0
        ensemble_confidence = weight_sum / len(predictions) if predictions else 0.0

        result = ModelPrediction(
            symbol=symbol,
            timestamp=datetime.now(),
            predictions=predictions,
            confidence_scores=confidences,
            ensemble_prediction=ensemble_prediction,
            ensemble_confidence=ensemble_confidence,
            metadata={
                "weights": self.weights,
                "models_active": len([p for p in predictions.values() if p != 0.0]),
            },
        )

        # MLOps: Record inference telemetry
        if self.mlops_enabled and self.model_manager:
            try:
                latency_ms = (datetime.now() - start_time).total_seconds() * 1000
                champion = self.model_manager.registry.get_champion_model(symbol)
                if champion:
                    self.model_manager.registry.record_inference(
                        symbol,
                        champion.version,
                        features.tail(1),  # Latest features only
                        ensemble_prediction,
                        None,  # Ground truth not available at inference time
                        latency_ms
                    )

                # Record prediction metric
                if mlops_metrics:
                    mlops_metrics.inc_counter("ensemble_predictions_total", {
                        "symbol": symbol,
                        "models_active": str(len(predictions))
                    })

                    mlops_metrics.observe_histogram("ensemble_prediction_latency_seconds",
                                                  latency_ms / 1000.0, {
                                                      "symbol": symbol
                                                  })
            except Exception as e:
                if mlops_logger:
                    mlops_logger.warning(f"Failed to record inference telemetry: {e}")

        audit_logger.info(
            "ensemble_prediction_generated",
            symbol=symbol,
            prediction=ensemble_prediction,
            confidence=ensemble_confidence,
            individual_predictions=predictions,
        )

        return result

    def update_weights(self, performance_metrics: dict[str, ModelPerformance]):
        """Update ensemble weights based on model performance"""
        total_score = 0
        model_scores = {}

        for model_name, perf in performance_metrics.items():
            # Combine accuracy and Sharpe ratio for scoring
            score = (perf.accuracy * 0.6) + (perf.sharpe_ratio * 0.4)
            model_scores[model_name] = max(0.1, score)  # Minimum weight
            total_score += model_scores[model_name]

        # Normalize to create new weights
        if total_score > 0:
            for model_name in self.weights:
                if model_name in model_scores:
                    self.weights[model_name] = model_scores[model_name] / total_score
                else:
                    self.weights[model_name] = 0.1  # Fallback weight

        audit_logger.info(
            "ensemble_weights_updated",
            new_weights=self.weights,
            performance_metrics={k: v.__dict__ for k, v in performance_metrics.items()},
        )

    def get_model_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all models in ensemble"""
        status = {}

        for model_name, model in self.models.items():
            status[model_name] = {
                "is_trained": getattr(model, "is_trained", False),
                "weight": self.weights.get(model_name, 0.0),
                "available": True,
            }

            # Add model-specific info
            if model_name == "xgboost" and hasattr(model, "feature_importance"):
                status[model_name]["feature_importance"] = model.feature_importance

        return status

    def save_models(self, model_dir: str = "backend/models/saved_models") -> dict[str, bool]:
        """Save all trained models to disk with model card"""
        import json
        from pathlib import Path

        results = {}
        model_path = Path(model_dir)
        model_path.mkdir(parents=True, exist_ok=True)

        # Create model card with metadata
        model_card = {
            "created_at": datetime.now().isoformat(),
            "ensemble_weights": self.weights,
            "model_status": self.get_model_status(),
            "training_metadata": {}
        }

        for model_name, model in self.models.items():
            try:
                if not getattr(model, 'is_trained', False):
                    results[model_name] = False
                    continue

                if model_name == "lstm" and TENSORFLOW_AVAILABLE:
                    # Save TensorFlow model
                    model_file = model_path / f"{model_name}_model.h5"
                    if model.model is not None:
                        model.model.save(str(model_file))
                        results[model_name] = True

                        # Add training history to model card
                        if hasattr(model, 'training_history') and model.training_history:
                            model_card["training_metadata"][model_name] = {
                                "final_loss": float(model.training_history.history['loss'][-1]),
                                "final_val_loss": float(model.training_history.history['val_loss'][-1]),
                                "epochs_trained": len(model.training_history.history['loss']),
                                "sequence_length": model.sequence_length,
                                "random_seed": model.random_seed
                            }
                    else:
                        results[model_name] = False

                elif model_name in ["xgboost", "random_forest"] and JOBLIB_AVAILABLE:
                    # Save sklearn/xgboost models using joblib
                    model_file = model_path / f"{model_name}_model.joblib"
                    if model.model is not None:
                        joblib.dump({
                            'model': model.model,
                            'scaler': getattr(model, 'scaler', None),
                            'feature_importance': getattr(model, 'feature_importance', None)
                        }, str(model_file))
                        results[model_name] = True

                        # Add model info to model card
                        model_card["training_metadata"][model_name] = {
                            "feature_importance": getattr(model, 'feature_importance', {}),
                            "is_trained": model.is_trained
                        }
                    else:
                        results[model_name] = False
                else:
                    results[model_name] = False

            except Exception as e:
                logging.error(f"Error saving {model_name} model: {e}")
                results[model_name] = False

        # Save model card
        try:
            with open(model_path / "model_card.json", 'w') as f:
                json.dump(model_card, f, indent=2)
            logging.info(f"Model card saved to {model_path / 'model_card.json'}")
        except Exception as e:
            logging.error(f"Error saving model card: {e}")

        audit_logger.info("ensemble_models_saved",
                         results=results,
                         model_dir=str(model_path),
                         timestamp=datetime.now())

        return results

    def load_models(self, model_dir: str = "backend/models/saved_models") -> dict[str, bool]:
        """Load all models from disk"""
        import json
        from pathlib import Path

        results = {}
        model_path = Path(model_dir)

        if not model_path.exists():
            logging.warning(f"Model directory {model_path} does not exist")
            return {name: False for name in self.models.keys()}

        # Load model card if available
        model_card_file = model_path / "model_card.json"
        model_card = {}
        if model_card_file.exists():
            try:
                with open(model_card_file) as f:
                    model_card = json.load(f)
                logging.info(f"Loaded model card from {model_card_file}")

                # Restore ensemble weights
                if "ensemble_weights" in model_card:
                    self.weights = model_card["ensemble_weights"]

            except Exception as e:
                logging.error(f"Error loading model card: {e}")

        for model_name, model in self.models.items():
            try:
                if model_name == "lstm" and TENSORFLOW_AVAILABLE:
                    # Load TensorFlow model
                    model_file = model_path / f"{model_name}_model.h5"
                    if model_file.exists():
                        model.model = keras.models.load_model(str(model_file))
                        model.is_trained = True
                        results[model_name] = True

                        # Restore metadata from model card
                        if model_name in model_card.get("training_metadata", {}):
                            metadata = model_card["training_metadata"][model_name]
                            model.sequence_length = metadata.get("sequence_length", model.sequence_length)
                            model.random_seed = metadata.get("random_seed", model.random_seed)
                    else:
                        results[model_name] = False

                elif model_name in ["xgboost", "random_forest"] and JOBLIB_AVAILABLE:
                    # Load sklearn/xgboost models using joblib
                    model_file = model_path / f"{model_name}_model.joblib"
                    if model_file.exists():
                        model_data = joblib.load(str(model_file))
                        model.model = model_data.get('model')
                        model.scaler = model_data.get('scaler')
                        model.feature_importance = model_data.get('feature_importance', {})
                        model.is_trained = True
                        results[model_name] = True
                    else:
                        results[model_name] = False
                else:
                    results[model_name] = False

            except Exception as e:
                logging.error(f"Error loading {model_name} model: {e}")
                results[model_name] = False

        audit_logger.info("ensemble_models_loaded",
                         results=results,
                         model_dir=str(model_path),
                         timestamp=datetime.now())

        return results

    # MLOps Registry Integration Methods

    def register_with_mlops(
        self,
        model_name: str,
        training_data: pd.DataFrame,
        features: pd.DataFrame,
        metrics: dict[str, float],
        version: str | None = None,
        train_window: dict[str, str] | None = None
    ) -> Any | None:  # Returns ModelVersion if successful
        """
        Register ensemble model with MLOps registry

        Args:
            model_name: Name to register the model under
            training_data: Training data used
            features: Feature data used
            metrics: Performance metrics
            version: Version string (auto-generated if None)
            train_window: Training time window info

        Returns:
            ModelVersion if registration successful, None otherwise
        """
        if not self.mlops_enabled or not self.model_manager:
            if mlops_logger:
                mlops_logger.warning("MLOps registration attempted but MLOps not available")
            return None

        try:
            # Prepare artifacts dictionary
            artifacts = {
                'ensemble_weights': self.weights,
                'model_config': {
                    'lstm_available': TENSORFLOW_AVAILABLE,
                    'xgboost_available': XGBOOST_AVAILABLE,
                    'sklearn_available': SKLEARN_AVAILABLE
                },
                'performance_history': self.performance_history[-10:] if self.performance_history else []
            }

            # Add individual model artifacts if available
            for model_name_key, model in self.models.items():
                if hasattr(model, 'model') and model.model is not None:
                    artifacts[f'{model_name_key}_trained'] = True
                    if hasattr(model, 'scaler') and model.scaler is not None:
                        artifacts[f'{model_name_key}_scaler'] = model.scaler
                    if hasattr(model, 'feature_importance'):
                        artifacts[f'{model_name_key}_feature_importance'] = model.feature_importance
                else:
                    artifacts[f'{model_name_key}_trained'] = False

            # Get feature dtypes
            feature_dtypes = {col: str(features[col].dtype) for col in features.columns}

            # Register with MLOps registry
            model_version = self.model_manager.registry.register_model(
                model_name,
                self,  # Register the entire ensemble
                training_data,
                metrics,
                train_window,
                artifacts
            )

            if mlops_logger:
                mlops_logger.info(f"Successfully registered ensemble model {model_name}", {
                    "version": model_version.version,
                    "artifact_hash": model_version.artifact_hash,
                    "features_count": len(features.columns)
                })

            return model_version

        except Exception as e:
            if mlops_logger:
                mlops_logger.error(f"Failed to register ensemble model {model_name}: {e}")
            return None

    def promote_to_champion(self, model_name: str, version: str) -> bool:
        """
        Promote a model version to champion status

        Args:
            model_name: Name of the model
            version: Version to promote

        Returns:
            True if promotion successful, False otherwise
        """
        if not self.mlops_enabled or not self.model_manager:
            return False

        try:
            success = self.model_manager.registry.promote_to_champion(model_name, version)

            if success and mlops_logger:
                mlops_logger.info(f"Promoted ensemble model {model_name} version {version} to champion")

            return success

        except Exception as e:
            if mlops_logger:
                mlops_logger.error(f"Failed to promote {model_name}/{version}: {e}")
            return False

    def get_champion_version(self, model_name: str) -> Any | None:  # Returns ModelVersion if found
        """
        Get the champion model version from registry

        Args:
            model_name: Name of the model

        Returns:
            ModelVersion if champion exists, None otherwise
        """
        if not self.mlops_enabled or not self.model_manager:
            return None

        try:
            champion = self.model_manager.registry.get_champion_model(model_name)
            return champion

        except Exception as e:
            if mlops_logger:
                mlops_logger.error(f"Failed to get champion for {model_name}: {e}")
            return None

    def load_from_registry(self, model_name: str, version: str | None = None) -> bool:
        """
        Load ensemble model from MLOps registry

        Args:
            model_name: Name of the model to load
            version: Specific version to load (uses champion if None)

        Returns:
            True if loading successful, False otherwise
        """
        if not self.mlops_enabled or not self.model_manager:
            return False

        try:
            # Get version to load
            if version is None:
                champion = self.model_manager.registry.get_champion_model(model_name)
                if not champion:
                    if mlops_logger:
                        mlops_logger.warning(f"No champion model found for {model_name}")
                    return False
                version = champion.version

            # Load artifacts
            model_obj, artifacts, metadata = self.model_manager.registry.load_artifacts(model_name, version)

            # Restore ensemble configuration
            if 'ensemble_weights' in artifacts:
                self.weights = artifacts['ensemble_weights']

            if 'performance_history' in artifacts:
                self.performance_history = artifacts['performance_history']

            # TODO: Restore individual model states if needed
            # This would require serializing the TensorFlow/sklearn models properly

            if mlops_logger:
                mlops_logger.info(f"Successfully loaded ensemble model {model_name}/{version} from registry")

            return True

        except Exception as e:
            if mlops_logger:
                mlops_logger.error(f"Failed to load {model_name}/{version or 'champion'} from registry: {e}")
            return False
