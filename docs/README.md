# Documentation Index

## Status

- **[PLATFORM_STATUS.md](PLATFORM_STATUS.md)** — Living status tracker (start here)

## Getting Started

- [Quick Start Guide](setup/QUICK_START.md) — Get up and running
- [Environment Setup](setup/ENVIRONMENT.md) — Configure environment variables
- [Database Setup](setup/DATABASE.md) — Database configuration
- [Authentication](setup/AUTHENTICATION.md) — Auth system setup
- [TLS Setup](setup/TLS_SETUP_GUIDE.md) — SSL/TLS configuration

## Architecture

- [System Overview](architecture/SYSTEM_OVERVIEW.md) — High-level architecture
- [Signal Aggregation](architecture/SIGNAL_AGGREGATION.md) — Signal processing design
- [WebSocket Guide](architecture/WEBSOCKET_GUIDE.md) — Real-time communication
- [Trading Algorithms](architecture/TRADING_ALGORITHMS.md) — Algorithm analysis

## Blueprints

- [Evolving Organism Blueprint](blueprints/EVOLVING_ORGANISM_BLUEPRINT.md) — Living Organism architecture (authoritative)
- [Strategic Roadmap](blueprints/FULL_LIVING_TRADING_ORGANISM_BLUEPRINT_AND_EXECUTION_PLAN.md) — Long-term roadmap

## Operations

- [Paper Trading Rollout](operations/PAPER_TRADING_ROLLOUT.md) — Paper trading setup
- [Operational Cadence](operations/OPERATIONAL_CADENCE.md) — Day-to-day operations
- [Post-Launch Monitoring](operations/POST_LAUNCH_MONITORING.md) — Monitoring guide

## Testing

- [Test Strategy](testing/TEST_STRATEGY.md) — Test tiers, markers, and run procedures

## Runbooks

- [Incident Response](runbooks/INCIDENT_RESPONSE.md) — Emergency procedures
- See `runbooks/` for all operational runbooks

## API

- [Rate Limits](API_RATE_LIMITS.md) — API rate limiting policies
- Interactive docs available at `http://localhost:8000/docs` when backend is running

## Archive

Historical audit reports, superseded blueprints, and session-specific documents are preserved in [`archive/`](archive/). These are kept for reference but are no longer actively maintained.

- `archive/audits/` — Past security and compliance audits
- `archive/historical/` — Session logs, resolution plans
- `archive/superseded/` — Superseded blueprints and plans

## Directory Structure

```
docs/
├── PLATFORM_STATUS.md      ← Living status tracker
├── README.md               ← This file
├── architecture/           ← System design docs
├── blueprints/             ← Organism blueprints and roadmap
├── operations/             ← Operational procedures
├── runbooks/               ← Emergency runbooks
├── setup/                  ← Installation and configuration
├── testing/                ← Test strategy and procedures
└── archive/                ← Historical/superseded documents
    ├── audits/
    ├── historical/
    └── superseded/
```
