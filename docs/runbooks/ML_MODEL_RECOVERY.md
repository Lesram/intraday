# ML Model Deployment & Recovery Runbook

## Overview
Procedures for deploying ML models, monitoring model health, and recovering from model-related issues in the trading platform.

## Model Types in Use

| Model Type | Purpose | Update Frequency | Risk Impact |
|------------|---------|------------------|-------------|
| Price Prediction | Signal generation | Daily retrain | High |
| Regime Detection | Market state classification | Weekly | Medium |
| Risk Scoring | Position sizing | Monthly | High |
| Ensemble | Combined signals | On-demand | High |

## Health Checks

```bash
# Overall model status
curl http://localhost:8000/api/v1/models/status -H "Authorization: Bearer $TOKEN"

# Specific model health
curl http://localhost:8000/api/v1/models/price-prediction/health -H "Authorization: Bearer $TOKEN"

# Model staleness check
curl http://localhost:8000/api/v1/models/staleness -H "Authorization: Bearer $TOKEN"
```

## Model Deployment

### Standard Deployment (Blue-Green)

```bash
# Step 1: Deploy new model to staging slot
curl -X POST http://localhost:8000/api/v1/models/deploy \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "price_prediction_v2",
    "model_path": "s3://models/price_prediction_v2.pkl",
    "slot": "staging",
    "validation_required": true
  }'

# Step 2: Run validation suite
curl -X POST http://localhost:8000/api/v1/models/validate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "price_prediction_v2", "slot": "staging"}'

# Step 3: Shadow test (run alongside production without trading)
curl -X POST http://localhost:8000/api/v1/models/shadow-test \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "price_prediction_v2",
    "duration_minutes": 60,
    "compare_with": "price_prediction_v1"
  }'

# Step 4: Promote to production (after shadow test passes)
curl -X POST http://localhost:8000/api/v1/models/promote \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "price_prediction_v2"}'
```

### Emergency Deployment (Skip Validation)

⚠️ **Only use when current model is completely broken**

```bash
curl -X POST http://localhost:8000/api/v1/models/deploy/emergency \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "price_prediction_fallback",
    "model_path": "s3://models/price_prediction_stable.pkl",
    "reason": "Current model producing invalid predictions"
  }'
```

## Model Rollback

### Scenario: Model Producing Bad Predictions

```bash
# Step 1: Check prediction quality
curl http://localhost:8000/api/v1/models/price-prediction/predictions/recent \
  -H "Authorization: Bearer $TOKEN" | jq '.predictions | map(.confidence) | add / length'

# Step 2: If average confidence < 0.3 or predictions seem wrong, rollback
curl -X POST http://localhost:8000/api/v1/models/rollback \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "price_prediction",
    "target_version": "v1.5.3",
    "reason": "Low prediction quality detected"
  }'

# Step 3: Verify rollback
curl http://localhost:8000/api/v1/models/price-prediction/version -H "Authorization: Bearer $TOKEN"
```

## Model Staleness Detection

Models become stale when:
- Training data is too old (>7 days for daily models)
- Market regime has shifted significantly
- Prediction accuracy dropped below threshold

### Check Staleness

```bash
# Automated staleness report
curl http://localhost:8000/api/v1/models/staleness/report -H "Authorization: Bearer $TOKEN"
```

### Trigger Retrain

```bash
# Request model retrain
curl -X POST http://localhost:8000/api/v1/models/retrain \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "price_prediction",
    "training_window_days": 90,
    "validation_split": 0.2,
    "priority": "high"
  }'

# Monitor retrain progress
curl http://localhost:8000/api/v1/models/retrain/status -H "Authorization: Bearer $TOKEN"
```

## Model Fallback Modes

When ML models fail, the system has fallback behaviors:

| Model | Fallback Behavior |
|-------|-------------------|
| Price Prediction | Use simple moving average signals |
| Regime Detection | Assume "normal" regime |
| Risk Scoring | Use conservative fixed sizing |
| Ensemble | Use best single model |

### Activate Fallback Mode

```bash
curl -X POST http://localhost:8000/api/v1/models/fallback/activate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "price_prediction", "fallback_type": "simple_sma"}'
```

### Deactivate Fallback (Resume ML)

```bash
curl -X POST http://localhost:8000/api/v1/models/fallback/deactivate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "price_prediction"}'
```

## Model Performance Monitoring

### Key Metrics

| Metric | Normal Range | Alert Threshold |
|--------|--------------|-----------------|
| Prediction latency (P99) | <50ms | >100ms |
| Prediction accuracy (rolling) | >55% | <50% |
| Signal-to-trade PnL correlation | >0.2 | <0.1 |
| Model load time | <5s | >15s |
| Memory usage | <2GB | >4GB |

### Grafana Dashboard Queries

```promql
# Prediction accuracy (7-day rolling)
avg_over_time(ml_model_accuracy{model="price_prediction"}[7d])

# Prediction latency
histogram_quantile(0.99, ml_model_prediction_latency_bucket)

# Model staleness (hours since last retrain)
time() - ml_model_last_training_timestamp
```

## Debugging Model Issues

### Model Producing NaN/Invalid Outputs

```python
# Connect to application and check model state
import asyncio
from backend.ml.model_manager import ModelManager

async def check_model():
    manager = ModelManager()
    model = await manager.get_model("price_prediction")
    
    # Check input normalization
    print(f"Feature scaler: {model.scaler}")
    
    # Test with sample data
    sample = {"close": 150.0, "volume": 1000000, "sma_20": 148.0}
    prediction = model.predict(sample)
    print(f"Sample prediction: {prediction}")

asyncio.run(check_model())
```

### Model Memory Leak

```bash
# Check model memory usage
docker-compose exec backend python -c "
import sys
from backend.ml.model_manager import ModelManager
manager = ModelManager()
for name, model in manager._models.items():
    print(f'{name}: {sys.getsizeof(model) / 1024 / 1024:.2f} MB')
"

# Force garbage collection
curl -X POST http://localhost:8000/api/v1/system/gc -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Scheduled Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| Daily retrain | 4:00 AM ET | Update price prediction |
| Weekly regime check | Sunday 6:00 AM ET | Regime model update |
| Hourly staleness check | :00 | Alert if models stale |
| Model backup | Daily 2:00 AM ET | S3 backup of all models |

## Escalation

| Issue | First Responder | Escalate To |
|-------|-----------------|-------------|
| Model not loading | On-call SRE | ML Engineering |
| Bad predictions | Trading Ops | Quant Team |
| Memory issues | On-call SRE | Platform Team |
| Staleness alerts | ML Engineering | Quant Lead |
