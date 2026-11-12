"""Symbol universe shared by the dashboard market scanner and the auto-breakout scanner.

Audit 2026-10-05 A6-01: moved out of ``backend/api/routes/scanner.py`` so that
service code (``backend/services/auto_breakout_scanner.py``) no longer imports
an API routes module. ``backend.api.routes.scanner.SCANNABLE_SYMBOLS`` still
resolves to this list.
"""

from __future__ import annotations

# Popular symbols to scan
SCANNABLE_SYMBOLS: list[str] = [
    'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'META', 'NVDA', 'JPM', 'V', 'WMT',
    'UNH', 'JNJ', 'PG', 'MA', 'HD', 'DIS', 'PYPL', 'BAC', 'ADBE', 'CRM',
    'NFLX', 'CMCSA', 'XOM', 'VZ', 'KO', 'PEP', 'T', 'INTC', 'CSCO', 'PFE',
    'ABT', 'MRK', 'TMO', 'COST', 'AVGO', 'NKE', 'CVX', 'MCD', 'DHR', 'LLY',
    'TXN', 'NEE', 'UNP', 'ORCL', 'PM', 'BMY', 'QCOM', 'LIN', 'HON', 'AMD'
]
