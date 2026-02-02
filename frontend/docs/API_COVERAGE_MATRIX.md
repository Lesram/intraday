# API Coverage Matrix - Frontend to Backend Mapping
**Created**: October 5, 2025  
**Purpose**: Map every UI feature to backend API endpoints and identify gaps  
**Status**: 🟢 In Progress

---

## Overview

This matrix documents the complete mapping between frontend features and backend API endpoints. It serves as the foundation for frontend development by identifying:
- ✅ **Ready**: Endpoints that exist and are operational
- ⚠️ **Partial**: Endpoints that exist but need enhancements
- ❌ **Missing**: Endpoints that need to be implemented

**Current Status Summary**:
- ✅ Ready: ~60% (core trading features)
- ⚠️ Partial: ~20% (needs enhancements)
- ❌ Missing: ~20% (RBAC, market data APIs, notifications, reporting)

---

## 🔐 Authentication & User Management

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **Login** | `/api/v1/auth/login` | POST | ✅ Ready | `{ email, password }` | `{ access_token, refresh_token, user }` | Returns JWT tokens + user profile |
| **Register** | `/api/v1/auth/register` | POST | ✅ Ready | `{ email, password, name }` | `{ user, message }` | Creates new user account |
| **Refresh Token** | `/api/v1/auth/token/refresh` | POST | ✅ Ready | `{ refresh_token }` | `{ access_token }` | Gets new access token |
| **Logout** | `/api/v1/auth/logout` | POST | ⚠️ Needs Implementation | `{ refresh_token }` | `{ success }` | Should invalidate refresh token server-side |
| **Get Current User** | `/api/v1/auth/me` | GET | ✅ Ready | Headers: `Authorization: Bearer {token}` | `{ id, email, name, role, permissions }` | Returns authenticated user profile |
| **Validate Token** | `/api/v1/auth/validate` | POST | ✅ Ready | `{ token }` | `{ valid: boolean, user? }` | Checks if token is valid |
| **Reset Password Request** | `/api/v1/auth/password/reset` | POST | ❌ Missing | `{ email }` | `{ message }` | Sends password reset email |
| **Reset Password Confirm** | `/api/v1/auth/password/reset/confirm` | POST | ❌ Missing | `{ token, new_password }` | `{ success }` | Completes password reset |
| **Change Password** | `/api/v1/auth/password/change` | PUT | ❌ Missing | `{ old_password, new_password }` | `{ success }` | Change password while logged in |
| **Enable MFA** | `/api/v1/auth/mfa/enable` | POST | ❌ Missing | - | `{ qr_code, backup_codes }` | Setup MFA |
| **Verify MFA** | `/api/v1/auth/mfa/verify` | POST | ❌ Missing | `{ code }` | `{ success }` | Verify MFA code during login |

---

## 💼 Trading - Orders

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **Submit Order** | `/api/v1/orders/submit` | POST | ✅ Ready | `{ symbol, side, quantity, order_type, price?, time_in_force }` | `{ order_id, status, message }` | Pre-trade validation included |
| **Get All Orders** | `/api/v1/orders` | GET | ✅ Ready | Query: `?status=open&symbol=AAPL&limit=50` | `{ orders: [...], total }` | Supports filtering |
| **Get Order by ID** | `/api/v1/orders/{id}` | GET | ✅ Ready | - | `{ order: {...} }` | Full order details |
| **Cancel Order** | `/api/v1/orders/{id}/cancel` | DELETE | ✅ Ready | - | `{ success, message }` | Attempts to cancel order |
| **Modify Order** | `/api/v1/orders/{id}/modify` | PUT | ⚠️ Needs Implementation | `{ price?, quantity? }` | `{ success, updated_order }` | Modify price/quantity |
| **Get Order History** | `/api/v1/orders/history` | GET | ✅ Ready | Query: `?from=2025-01-01&to=2025-12-31&symbol=AAPL` | `{ orders: [...], total }` | Historical orders |
| **Get Order Fills** | `/api/v1/orders/{id}/fills` | GET | ⚠️ Partial | - | `{ fills: [...] }` | Execution details - needs enhancement |
| **Bulk Cancel Orders** | `/api/v1/orders/cancel-all` | POST | ❌ Missing | `{ symbol?, side? }` | `{ cancelled_count }` | Cancel multiple orders |
| **Pre-Trade Validation** | `/api/v1/orders/validate` | POST | ⚠️ Built into submit | Same as submit | `{ valid, errors?, warnings? }` | Currently part of submit, should be separate |

---

## 📊 Portfolio & Positions

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **Get All Positions** | `/api/v1/positions` | GET | ✅ Ready | - | `{ positions: [...] }` | All open positions with real-time P&L |
| **Get Position by Symbol** | `/api/v1/positions/{symbol}` | GET | ✅ Ready | - | `{ position: {...} }` | Detailed position info |
| **Close Position** | `/api/v1/positions/{symbol}/close` | POST | ⚠️ Needs Implementation | `{ method: 'market' \| 'limit', price? }` | `{ order_id }` | Should submit closing order |
| **Get Portfolio Summary** | `/api/v1/portfolio` | GET | ✅ Ready | - | `{ equity, cash, buying_power, daily_pl, total_pl }` | Real-time portfolio metrics |
| **Get Portfolio History** | `/api/v1/portfolio/history` | GET | ❌ Missing | Query: `?from=2025-01-01&to=2025-12-31&interval=1d` | `{ data: [{timestamp, equity, pl}] }` | Time-series equity data for charts |
| **Get Performance Metrics** | `/api/v1/portfolio/metrics` | GET | ⚠️ Partial | Query: `?period=30d` | `{ sharpe, sortino, max_drawdown, win_rate, ... }` | Needs more comprehensive metrics |
| **Get Holdings** | `/api/v1/portfolio/holdings` | GET | ✅ Ready | - | Same as positions | Alias for positions |
| **Get P&L Attribution** | `/api/v1/portfolio/attribution` | GET | ❌ Missing | Query: `?period=1M&group_by=strategy` | `{ data: [{label, pl, percent}] }` | P&L breakdown by strategy/asset |
| **Get Correlation Matrix** | `/api/v1/portfolio/correlation` | GET | ❌ Missing | - | `{ matrix: [[...]] }` | Position correlation analysis |

---

## 🤖 Strategy Management

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **List All Strategies** | `/api/v1/strategies` | GET | ✅ Ready | Query: `?category=momentum&status=active` | `{ strategies: [...] }` | All available strategies |
| **Get Strategy Details** | `/api/v1/strategies/{id}` | GET | ✅ Ready | - | `{ strategy: {...}, config, performance }` | Full strategy info |
| **Create Strategy** | `/api/v1/strategies` | POST | ⚠️ Partial | `{ name, type, config, parameters }` | `{ strategy_id }` | Needs validation |
| **Update Strategy** | `/api/v1/strategies/{id}` | PUT | ✅ Ready | `{ config?, parameters? }` | `{ success }` | Update config |
| **Delete Strategy** | `/api/v1/strategies/{id}` | DELETE | ⚠️ Needs Implementation | - | `{ success }` | Delete custom strategy |
| **Start Strategy** | `/api/v1/strategies/{id}/start` | POST | ✅ Ready | `{ symbols?, risk_params? }` | `{ success, message }` | Begin execution |
| **Stop Strategy** | `/api/v1/strategies/{id}/stop` | POST | ✅ Ready | - | `{ success, message }` | Halt execution |
| **Pause Strategy** | `/api/v1/strategies/{id}/pause` | POST | ⚠️ Needs Implementation | - | `{ success }` | Temporarily pause |
| **Get Strategy Status** | `/api/v1/strategies/{id}/status` | GET | ✅ Ready | - | `{ status, positions, pl, signals }` | Current execution state |
| **Get Strategy Signals** | `/api/v1/strategies/{id}/signals` | GET | ✅ Ready | Query: `?limit=50` | `{ signals: [...] }` | Recent signals |
| **Run Backtest** | `/api/v1/strategies/{id}/backtest` | POST | ⚠️ Partial | `{ start_date, end_date, initial_capital, symbols }` | `{ backtest_id }` | Starts backtest job |
| **Get Backtest Results** | `/api/v1/strategies/backtests/{id}` | GET | ❌ Missing | - | `{ results: {...}, equity_curve, trades }` | Retrieve backtest results |
| **List Backtests** | `/api/v1/strategies/{id}/backtests` | GET | ❌ Missing | - | `{ backtests: [...] }` | Historical backtests for strategy |

---

## 🧠 ML Models

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **List All Models** | `/api/v1/models` | GET | ✅ Ready | - | `{ models: [...] }` | Model registry |
| **Get Model Details** | `/api/v1/models/{id}` | GET | ✅ Ready | - | `{ model: {...}, metrics, features }` | Detailed model info |
| **Get Model Status** | `/api/v1/models/status` | GET | ✅ Ready | - | `{ models: [{id, status, accuracy}] }` | All models status |
| **Get Predictions** | `/api/v1/models/{id}/predict` | POST | ✅ Ready | `{ symbol, features? }` | `{ prediction, confidence, timestamp }` | Real-time prediction |
| **Batch Predictions** | `/api/v1/models/{id}/predict/batch` | POST | ⚠️ Needs Implementation | `{ symbols: [...] }` | `{ predictions: [...] }` | Multiple symbol predictions |
| **Train Model** | `/api/v1/models/{id}/train` | POST | ✅ Ready | `{ data_source, start_date, end_date, params }` | `{ job_id, status }` | Trigger training |
| **Get Training Status** | `/api/v1/models/{id}/training/{job_id}` | GET | ⚠️ Needs Implementation | - | `{ status, progress, eta }` | Training job status |
| **Get Model Performance** | `/api/v1/models/{id}/performance` | GET | ⚠️ Partial | Query: `?period=30d` | `{ accuracy, precision, recall, f1 }` | Needs more metrics |
| **Get Feature Importance** | `/api/v1/models/{id}/features` | GET | ⚠️ Needs Implementation | - | `{ features: [{name, importance}] }` | Feature analysis |
| **Configure Ensemble** | `/api/v1/models/ensemble` | PUT | ⚠️ Needs Implementation | `{ models: [{id, weight}], voting_method }` | `{ success }` | Ensemble configuration |
| **Get Ensemble Predictions** | `/api/v1/models/ensemble/predict` | POST | ⚠️ Partial | `{ symbol }` | `{ prediction, model_votes }` | Ensemble prediction |

---

## ⚠️ Risk Management

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **Get Risk Metrics** | `/api/v1/risk/metrics` | GET | ✅ Ready | - | `{ daily_pl, max_drawdown, var, leverage, exposure }` | Current risk levels |
| **Get Risk Limits** | `/api/v1/risk/limits` | GET | ✅ Ready | - | `{ limits: {...} }` | Configured risk limits |
| **Update Risk Limits** | `/api/v1/risk/limits` | PUT | ✅ Ready | `{ daily_loss_limit?, position_limit?, ... }` | `{ success }` | Admin only |
| **Get Guardrails Status** | `/api/v1/risk/guardrails` | GET | ⚠️ Needs Implementation | - | `{ active, triggered, circuit_breakers }` | Circuit breaker status |
| **Trigger Emergency Stop** | `/api/v1/risk/emergency-stop` | POST | ⚠️ Needs Implementation | `{ reason }` | `{ success, stopped_strategies }` | Kill switch |
| **Reset Guardrail** | `/api/v1/risk/guardrails/{id}/reset` | POST | ⚠️ Needs Implementation | `{ confirmation }` | `{ success }` | Admin only - reset triggered guardrail |
| **Get Risk Violations** | `/api/v1/risk/violations` | GET | ❌ Missing | Query: `?from=2025-01-01&limit=50` | `{ violations: [...] }` | Historical violations log |
| **Get Position Limits** | `/api/v1/risk/limits/positions` | GET | ⚠️ Partial | - | `{ limits: {...} }` | Per-symbol/sector limits |
| **Get Exposure Analysis** | `/api/v1/risk/exposure` | GET | ❌ Missing | - | `{ by_sector, by_asset_class, concentration }` | Portfolio exposure breakdown |

---

## 📡 Market Data & Real-Time Quotes

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **Get Real-Time Quote** | `/api/v1/market-data/quote/{symbol}` | GET | ❌ Missing | - | `{ symbol, price, bid, ask, volume, timestamp }` | Live quote |
| **Get Batch Quotes** | `/api/v1/market-data/quotes` | POST | ❌ Missing | `{ symbols: [...] }` | `{ quotes: [...] }` | Multiple symbols |
| **Get Historical Bars** | `/api/v1/market-data/history` | GET | ❌ Missing | Query: `?symbol=AAPL&interval=1d&from=2025-01-01&to=2025-12-31` | `{ bars: [{time, open, high, low, close, volume}] }` | OHLCV data for charts |
| **Get Technical Indicators** | `/api/v1/market-data/indicators` | GET | ❌ Missing | Query: `?symbol=AAPL&indicators=sma_20,rsi,macd` | `{ data: [{time, indicators: {...}}] }` | Calculated indicators |
| **Get Market Status** | `/api/v1/market-data/status` | GET | ⚠️ Needs Implementation | - | `{ is_open, next_open, next_close }` | Market hours |
| **Get Symbol Info** | `/api/v1/market-data/symbols/{symbol}` | GET | ❌ Missing | - | `{ name, exchange, sector, market_cap, ... }` | Symbol metadata |
| **Search Symbols** | `/api/v1/market-data/symbols/search` | GET | ❌ Missing | Query: `?q=AAPL` | `{ results: [...] }` | Symbol search for autocomplete |
| **Get Order Book (L2)** | `/api/v1/market-data/orderbook/{symbol}` | GET | ❌ Missing | - | `{ bids: [...], asks: [...] }` | Level 2 market depth |
| **Get Recent Trades** | `/api/v1/market-data/trades/{symbol}` | GET | ❌ Missing | Query: `?limit=100` | `{ trades: [{time, price, size}] }` | Time & sales |

---

## 📰 News & Sentiment

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **Get News Feed** | `/api/v1/news` | GET | ❌ Missing | Query: `?symbols=AAPL,TSLA&limit=50` | `{ articles: [...] }` | Filtered news feed |
| **Get Article** | `/api/v1/news/{id}` | GET | ❌ Missing | - | `{ article: {...}, sentiment }` | Full article content |
| **Get Sentiment Score** | `/api/v1/sentiment/{symbol}` | GET | ❌ Missing | - | `{ score, trend, volume }` | Current sentiment |
| **Get Sentiment History** | `/api/v1/sentiment/{symbol}/history` | GET | ❌ Missing | Query: `?period=30d` | `{ data: [{time, score}] }` | Historical sentiment |
| **Get Market Sentiment** | `/api/v1/sentiment/market` | GET | ❌ Missing | - | `{ overall, by_sector, fear_greed_index }` | Broad market sentiment |

---

## 🔧 System Administration (Admin Only)

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **List All Users** | `/api/v1/admin/users` | GET | ❌ Missing | Query: `?role=trader&status=active` | `{ users: [...] }` | **RBAC not implemented** |
| **Get User Details** | `/api/v1/admin/users/{id}` | GET | ❌ Missing | - | `{ user: {...}, activity }` | **RBAC not implemented** |
| **Create User** | `/api/v1/admin/users` | POST | ❌ Missing | `{ email, name, role, permissions }` | `{ user_id }` | **RBAC not implemented** |
| **Update User** | `/api/v1/admin/users/{id}` | PUT | ❌ Missing | `{ role?, status?, permissions? }` | `{ success }` | **RBAC not implemented** |
| **Delete/Deactivate User** | `/api/v1/admin/users/{id}` | DELETE | ❌ Missing | - | `{ success }` | **RBAC not implemented** |
| **Generate API Key** | `/api/v1/admin/api-keys` | POST | ❌ Missing | `{ name, permissions, expiry }` | `{ api_key, secret }` | Programmatic access |
| **List API Keys** | `/api/v1/admin/api-keys` | GET | ❌ Missing | - | `{ keys: [...] }` | Show keys (masked) |
| **Revoke API Key** | `/api/v1/admin/api-keys/{id}` | DELETE | ❌ Missing | - | `{ success }` | Revoke key |
| **Get System Config** | `/api/v1/admin/config` | GET | ❌ Missing | - | `{ config: {...} }` | Global settings |
| **Update System Config** | `/api/v1/admin/config` | PUT | ❌ Missing | `{ key, value }` | `{ success }` | Update settings |
| **Get System Health** | `/api/v1/admin/health` | GET | ⚠️ Partial (public `/health`) | - | `{ status, services, uptime }` | System monitoring |
| **Get Audit Logs** | `/api/v1/admin/audit` | GET | ⚠️ Needs Implementation | Query: `?user_id=123&action=order&from=2025-01-01` | `{ logs: [...] }` | **Logs exist, need API** |

---

## 📊 Reporting & Analytics

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **List Reports** | `/api/v1/reports` | GET | ❌ Missing | - | `{ reports: [...] }` | Available reports |
| **Generate Report** | `/api/v1/reports/generate` | POST | ❌ Missing | `{ type, parameters, format: 'pdf'\|'excel' }` | `{ report_id, status }` | Async report generation |
| **Get Report Status** | `/api/v1/reports/{id}/status` | GET | ❌ Missing | - | `{ status, progress, url? }` | Job status |
| **Download Report** | `/api/v1/reports/{id}/download` | GET | ❌ Missing | - | File stream | Download generated report |
| **Schedule Report** | `/api/v1/reports/schedule` | POST | ❌ Missing | `{ type, schedule, recipients }` | `{ schedule_id }` | Automated reports |
| **Get Performance Report** | `/api/v1/reports/performance` | GET | ❌ Missing | Query: `?period=1M` | `{ data: {...} }` | Pre-built performance report |
| **Get Risk Report** | `/api/v1/reports/risk` | GET | ❌ Missing | Query: `?date=2025-10-01` | `{ data: {...} }` | Daily risk report |
| **Get Execution Quality Report** | `/api/v1/reports/execution` | GET | ❌ Missing | Query: `?period=1M` | `{ slippage, fill_rate, latency }` | Trading execution analysis |
| **Export Data** | `/api/v1/export/{entity}` | GET | ❌ Missing | Query: `?format=csv&from=2025-01-01` | File stream | Generic data export (orders, trades, positions) |

---

## 🔔 Notifications & Alerts

| UI Feature | Endpoint | Method | Status | Request | Response | Notes |
|------------|----------|--------|--------|---------|----------|-------|
| **Get Notifications** | `/api/v1/notifications` | GET | ❌ Missing | Query: `?unread=true&limit=50` | `{ notifications: [...] }` | **Notification service not built** |
| **Get Notification Count** | `/api/v1/notifications/count` | GET | ❌ Missing | - | `{ unread_count }` | Badge count |
| **Mark as Read** | `/api/v1/notifications/{id}/read` | POST | ❌ Missing | - | `{ success }` | Mark notification read |
| **Mark All as Read** | `/api/v1/notifications/read-all` | POST | ❌ Missing | - | `{ success }` | Clear all notifications |
| **Delete Notification** | `/api/v1/notifications/{id}` | DELETE | ❌ Missing | - | `{ success }` | Remove notification |
| **Get Alert Preferences** | `/api/v1/notifications/preferences` | GET | ❌ Missing | - | `{ preferences: {...} }` | User notification settings |
| **Update Alert Preferences** | `/api/v1/notifications/preferences` | PUT | ❌ Missing | `{ email_enabled, sms_enabled, events: [...] }` | `{ success }` | Configure notifications |
| **Create Custom Alert** | `/api/v1/alerts` | POST | ❌ Missing | `{ type, condition, threshold, channels }` | `{ alert_id }` | Price alerts, etc. |
| **List Custom Alerts** | `/api/v1/alerts` | GET | ❌ Missing | - | `{ alerts: [...] }` | User's custom alerts |
| **Delete Custom Alert** | `/api/v1/alerts/{id}` | DELETE | ❌ Missing | - | `{ success }` | Remove alert |

---

## 🌐 WebSocket Real-Time Subscriptions

| Topic | Message Type | Status | Purpose | Notes |
|-------|--------------|--------|---------|-------|
| **Connection** | `ws://localhost:8000/ws/realtime/{client_id}` | ⚠️ Partial | WebSocket endpoint | Architecture exists, needs topic implementation |
| **orders** | `order_update` | ⚠️ Needs Implementation | Real-time order status changes | When order filled/cancelled/rejected |
| **positions** | `position_update` | ⚠️ Needs Implementation | Real-time position P&L updates | Every 1-5 seconds or on changes |
| **portfolio** | `portfolio_update` | ⚠️ Needs Implementation | Portfolio-level updates | Equity, cash, P&L changes |
| **market_data** | `price_update` | ❌ Missing | Live price ticks for watched symbols | 1-2 second intervals |
| **signals** | `signal_generated` | ⚠️ Needs Implementation | New trading signals from strategies | Real-time as generated |
| **alerts** | `alert` | ❌ Missing | System/risk alerts and notifications | Critical events |
| **strategies** | `strategy_update` | ⚠️ Needs Implementation | Strategy execution events | Status changes, new positions |
| **risk** | `risk_update` | ❌ Missing | Risk metric changes | When approaching limits |

---

## 📈 Summary & Priority Backend Work

### ✅ Ready for Frontend Development (60%)
Core trading functionality is operational:
- Authentication (JWT)
- Order submission & management
- Position tracking
- Portfolio summary
- Strategy management (start/stop/configure)
- ML model predictions
- Risk metrics & limits
- Basic backtesting

### ⚠️ Needs Enhancement (20%)
These endpoints exist but need expansion:
1. **WebSocket Topics** - Architecture ready, need topic implementations
2. **Backtest Results Storage** - Can run backtests, need result retrieval
3. **Order Modification** - Need ability to modify price/quantity
4. **Position Closing** - Need dedicated endpoint (not just order submission)
5. **Portfolio History** - Need time-series data for charts
6. **Model Training Status** - Need async job status tracking
7. **Audit Log API** - Logs exist, need query interface

### ❌ Critical Missing (20%)
These are required for complete platform:

**HIGH PRIORITY** (Blocks major features):
1. **RBAC System** - User roles, permissions, admin management (10+ endpoints)
2. **Market Data APIs** - Real-time quotes, historical bars, technical indicators (8+ endpoints)
3. **Notification Service** - In-app notifications, preferences, custom alerts (10+ endpoints)
4. **WebSocket Real-Time Streams** - Order updates, position updates, price data, alerts

**MEDIUM PRIORITY** (Nice to have):
5. **Reporting System** - Generate/download reports, scheduling (7+ endpoints)
6. **News & Sentiment** - Feed integration, sentiment analysis (5+ endpoints)
7. **Advanced Risk** - Exposure analysis, violation log, guardrail management (4+ endpoints)

---

## 🎯 Recommendations

### For Frontend Team:
1. **Phase 1-2**: Focus on ✅ Ready endpoints (auth, orders, positions, dashboard)
2. **Phase 3**: Work with ⚠️ Partial endpoints (use workarounds, request enhancements)
3. **Phase 4**: Stub UI for ❌ Missing features (show coming soon, use mock data)
4. **Phase 5**: Integrate as backend endpoints become available

### For Backend Team:
**Week 1-2** (Critical Path):
- Implement WebSocket topic subscriptions (orders, positions, signals)
- Add order modification endpoint
- Add position close endpoint
- Add portfolio history endpoint

**Week 3-4** (High Priority):
- Implement market data API (quotes, historical bars)
- Begin RBAC implementation (users, roles, permissions)
- Add notification service foundation

**Week 5-6** (Medium Priority):
- Complete RBAC implementation
- Add reporting system
- Enhance backtest result storage/retrieval

---

**Last Updated**: October 5, 2025  
**Maintainer**: Frontend Team Lead  
**Review Schedule**: Weekly during Phase 1-2, then bi-weekly
