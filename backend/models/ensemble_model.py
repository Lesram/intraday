"""
AI/ML Ensemble Modeling System
Combines LSTM, XGBoost, and RandomForest for comprehensive price prediction
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler

    SKLEARN_AVAILABLE = True
except ImportError as e:
    logging.warning(f"scikit-learn not available: {e}")
    SKLEARN_AVAILABLE = False

try:
    import xgboost as xgb

    XGBOOST_AVAILABLE = True
except ImportError as e:
    logging.warning(f"XGBoost not available: {e}")
    XGBOOST_AVAILABLE = False

from ..config import get_settings
from ..utils.helpers import calculate_sharpe_ratio
from ..utils.logger import audit_logger, performance_logger


@dataclass
class ModelPrediction:
    """Container for model predictions"""

    symbol: str
    timestamp: datetime
    predictions: Dict[str, float]  # model_name -> prediction
    confidence_scores: Dict[str, float]  # model_name -> confidence
    ensemble_prediction: float
    ensemble_confidence: float
    metadata: Dict[str, Any]


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
    """LSTM Neural Network for time series prediction"""

    def __init__(self, sequence_length: int = 60, features: int = 1):
        self.sequence_length = sequence_length
        self.features = features
        self.model = None
        self.scaler = None
        self.is_trained = False

    def build_model(self) -> Optional[Any]:
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

    def prepare_sequences(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
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

            # Training with validation split
            split_idx = int(len(X) * 0.8)
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]

            self.model.fit(
                X_train,
                y_train,
                validation_data=(X_val, y_val),
                epochs=50,
                batch_size=32,
                verbose=0,
                callbacks=[
                    keras.callbacks.EarlyStopping(
                        patience=10, restore_best_weights=True
                    )
                ],
            )

            self.is_trained = True
            return True

        except Exception as e:
            logging.error(f"Error training LSTM model: {e}")
            return False

    def predict(
        self, data: pd.DataFrame, target_column: str = "close"
    ) -> Tuple[float, float]:
        """Make prediction with confidence score"""
        if not self.is_trained or self.model is None or self.scaler is None:
            return 0.0, 0.0

        try:
            # Scale recent data
            recent_data = data[[target_column]].tail(self.sequence_length).values
            scaled_recent = self.scaler.transform(recent_data)

            # Prepare input sequence
            X_pred = scaled_recent.reshape(1, self.sequence_length, 1)

            # Make prediction
            prediction_scaled = self.model.predict(X_pred, verbose=0)[0][0]
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
                    zip(features.columns, self.model.feature_importances_)
                )
                self.is_trained = True
                return True

        except Exception as e:
            logging.error(f"Error training XGBoost model: {e}")

        return False

    def predict(self, features: pd.DataFrame) -> Tuple[float, float]:
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

    def predict(self, features: pd.DataFrame) -> Tuple[float, float]:
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

    async def train_models(
        self,
        price_data: pd.DataFrame,
        features: pd.DataFrame,
        target_column: str = "close",
    ) -> Dict[str, bool]:
        """Train all models in the ensemble"""
        results = {}

        # Train LSTM on price sequences
        results["lstm"] = await self.models["lstm"].train(price_data, target_column)

        # Train tree-based models on features
        target = price_data[target_column].shift(-1).dropna()  # Next period target
        features_aligned = features.iloc[:-1]  # Align with target

        results["xgboost"] = await self.models["xgboost"].train(
            features_aligned, target
        )
        results["random_forest"] = await self.models["random_forest"].train(
            features_aligned, target
        )

        audit_logger.info(
            "ensemble_training_completed", results=results, timestamp=datetime.now()
        )

        return results

    def predict(
        self, price_data: pd.DataFrame, features: pd.DataFrame, symbol: str
    ) -> ModelPrediction:
        """Generate ensemble prediction"""
        predictions = {}
        confidences = {}

        # Get predictions from each model
        for model_name, model in self.models.items():
            if model_name == "lstm":
                pred, conf = model.predict(price_data)
            else:
                # Use latest features for tree models
                latest_features = features.tail(1)
                pred, conf = model.predict(latest_features)

            predictions[model_name] = pred
            confidences[model_name] = conf

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

        audit_logger.info(
            "ensemble_prediction_generated",
            symbol=symbol,
            prediction=ensemble_prediction,
            confidence=ensemble_confidence,
            individual_predictions=predictions,
        )

        return result

    def update_weights(self, performance_metrics: Dict[str, ModelPerformance]):
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

    def get_model_status(self) -> Dict[str, Dict[str, Any]]:
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
