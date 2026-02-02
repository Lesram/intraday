#!/usr/bin/env python3
"""Check which modules import successfully"""
import sys

modules = [
    'backend.api.routes.admin_trading',
    'backend.api.routes.auth',
    'backend.api.routes.backtest',
    'backend.api.routes.chart_templates',
    'backend.api.routes.drawings',
    'backend.api.routes.health',
    'backend.api.routes.indicators',
    'backend.api.routes.lots',
    'backend.api.routes.market_data',
    'backend.api.routes.models',
    'backend.api.routes.monitoring',
    'backend.api.routes.observability',
    'backend.api.routes.orders',
    'backend.api.routes.position_import',
    'backend.api.routes.positions',
    'backend.api.routes.risk',
    'backend.api.routes.scanner',
    'backend.api.routes.signals',
    'backend.api.routes.strategy',
    'backend.api.routes.system',
    'backend.api.routes.trades',
    'backend.api.routes.watchlists',
    'backend.api.routes.audit',
    'backend.services.order_service',
    'backend.services.risk_manager',
    'backend.services.backtest_service',
    'backend.ml.model_manager',
    'backend.ml.ensemble_model',
]

print('=== MODULE IMPORT CHECK ===')
failed = []
for mod in modules:
    try:
        __import__(mod)
        short = mod.split('.')[-1]
        print(f'  OK: {short}')
    except Exception as e:
        short = mod.split('.')[-1]
        err = str(e)[:60]
        failed.append((mod, err))
        print(f'FAIL: {short} - {err}')

print(f'\n{len(modules)-len(failed)} OK, {len(failed)} FAILED')
if failed:
    print('\nFailed modules:')
    for m, e in failed:
        print(f'  {m}: {e}')
