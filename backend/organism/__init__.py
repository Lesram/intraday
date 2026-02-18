"""
Living Trading Organism — Full autonomous learning system.

Modules:
- attribution:       Fill-based P&L attribution per strategy × symbol × time
- brain_persistence: Cross-run cumulative learning persistence (save/load brain)
- self_evolution:    Meta-learning engine — adapts ALL tunable parameters from
                     trade outcome evidence (signal weights, exit params, feature
                     selection, regime sizing, symbol fitness, entry thresholds)
"""
