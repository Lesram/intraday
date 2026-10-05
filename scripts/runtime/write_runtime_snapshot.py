#!/usr/bin/env python3
"""Runtime config snapshot writer.

Produces FOUR snapshot files:
  artifacts/runtime_defaults_snapshot.json     — code defaults (offline, from source)
  artifacts/resolved_config_snapshot.json      — env > .env > code defaults resolution
  artifacts/live_process_runtime_snapshot.json  — live values from the running process
  artifacts/runtime_config_snapshot.json        — flat resolved config (legacy compat)

Used by CI, post-close audit, and daily reports to verify live behavior
matches documented spec.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

# Allow imports from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)


def _build_defaults_snapshot() -> dict:
    """Build snapshot from code defaults (no container required)."""
    try:
        from backend.organism.adaptive_exits import AdaptiveExitEngine
        from backend.organism.alpha_scanner import AlphaScanner
        from backend.organism.close_accounting import ACCOUNTING_POLICY
        from backend.organism.composite_indicators import COMPOSITE_COLUMNS
        from backend.organism.entry_freshness import ENTRY_TIMEFRAME, MAX_ENTRY_BAR_AGE_SECONDS
        from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
        from backend.integrations import alpaca_outbox as _outbox_dispatch
        from backend.infra import outbox_worker as _outbox_worker
        from backend.integrations import alpaca_stream as _fill_ingestion
        from backend.organism import live_engine_fills as _fill_lookup
        from backend.organism.streaming_data_provider import StreamingDataProvider
        from backend.organism import streaming_data_provider as _provider_module
        from backend.organism import live_engine as _engine_module
        from backend.infra import runtime_identity as _runtime_identity
        from backend.organism import operator_cancellation
        from scripts.phase2_freeze import compute_data_pipeline_sources
        from backend.organism.research_policy import policy_status
        from backend.organism.governance import (
            DEFAULT_DRAWDOWN_COOLDOWN_S,
            DEFAULT_DRAWDOWN_KILL_PCT,
            DEFAULT_MAX_CHANGES_PER_DAY,
        )
        from backend.organism.kelly_sizer import KellySizer
        from backend.organism.trading_phase import (
            EVOLUTION_FREEZE_TRADES,
            PROMOTION_MIN_LAST_50_MEAN_PNL,
            PROMOTION_MIN_LAST_50_WIN_RATE,
            PROMOTION_MIN_SHARPE_PER_TRADE,
            PROMOTION_MIN_TOTAL_PNL,
            ML_ISOLATION_TRADES,
        )
        from backend.organism.live_engine import (
            OrganismLiveEngine,
            ALPHA_TOP_N,
            ALPHA_BREAKOUT_BAD_REGIME_FILTER_ENABLED,
            CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED,
            CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH,
            EXPLORATION_ENABLED,
            LIVE_LOOKBACK,
            LIVE_TIMEFRAME,
            LIVE_UNIVERSE_CSV,
            LONG_ONLY,
            MAX_DAILY_LOSS,
            MAX_NOTIONAL_PER_TRADE,
            MAX_OPEN_POSITIONS,
            MIN_BARS,
            PREDICTION_HORIZON,
            PHASE9_SHADOW_ENGINES_ENABLED,
            RETRAIN_INTERVAL,
            STRATEGY_EVIDENCE_TELEMETRY_ENABLED,
            STRATEGY_EVIDENCE_TELEMETRY_PATH,
            USE_STREAMING,
        )

        return {
            "source": "code_defaults",
            "close_accounting_policy": ACCOUNTING_POLICY,
            # Checked-out source identity only. A running process must be
            # bound to this candidate before these hashes describe deployment.
            "candidate_data_pipeline_sources": compute_data_pipeline_sources(),
            "composite_feature_columns": list(COMPOSITE_COLUMNS),
            "pending_entry_resolution": {
                "call_timeout_seconds": operator_cancellation.CALL_TIMEOUT,
                "total_timeout_seconds": operator_cancellation.TOTAL_TIMEOUT,
                "confirmation_attempts": operator_cancellation.CONFIRM_ATTEMPTS,
                "inventory_limit": operator_cancellation.INVENTORY_LIMIT,
                "filled_entry_cooldown": "preserve_engine_pending_entry_ticks",
                "expiry": "unresolved_identity_never_expires_by_time",
                # Audit 2026-09-30 EXE-03: visibility, not retirement.
                "age_escalation_min_seconds": OrganismLiveEngine._PENDING_ENTRY_ESCALATE_SECONDS,
                "age_escalation": "one_critical_per_identity_older_than_max(min_seconds,2x_pending_entry_ticks_x_tick_interval)_first_seen_persisted_across_restarts",
                "release": "broker_terminal_and_exact_accounting_exposure_confirmation",
                # Audit 2026-10-05 C04-01: an entry the outbox never delivered.
                "never_sent_release": "outbox_worker_finalized_absence_proof_and_zero_fills_on_a_later_tick_than_registration_or_restore",
                "never_sent_statuses": list(operator_cancellation.NEVER_SENT_STATUSES),
                "ordinary_reconciliation": "read_only_after_fill_accounting",
                "retry_order": "resume_after_last_attempted_identity",
            },
            "streaming_subscription_sync": {
                "timeout_seconds": OrganismLiveEngine._STREAM_SUBSCRIPTION_SYNC_TIMEOUT_S,
                "ack_timeout_seconds": AlpacaMarketDataStream.SUBSCRIPTION_ACK_TIMEOUT_S,
                "subscription_retry_interval_seconds": AlpacaMarketDataStream.SUBSCRIPTION_RETRY_INTERVAL_S,
                "startup_retry_interval_seconds": StreamingDataProvider.STARTUP_RETRY_INTERVAL_S,
                "startup_timeout_seconds": StreamingDataProvider.STARTUP_TIMEOUT_S,
                "completion": "provider_confirmed_bars_and_quotes_current_connection",
                "unsubscribe": "retain_until_provider_confirmed_removal",
                "historical_prefill": "history_only_never_a_live_receipt",
                "universe": "critical_then_held_then_pending_within_cap_then_core_then_scanner_window_then_base_bounded_by_cap",
                "scanner_window_order": "current_scan_existing_members_first_then_newcomers_by_rank_then_older_by_recency",
                "stream_max_symbols": _engine_module.STREAM_MAX_SYMBOLS,
                "provider_max_symbols": _provider_module.MAX_STREAM_SYMBOLS,
                "critical_symbols": list(_engine_module.STREAM_CRITICAL_SYMBOLS),
                "scanner_window_max": _engine_module.SCANNER_WINDOW_MAX,
                "scanner_window_ttl_scans": _engine_module.SCANNER_WINDOW_TTL_SCANS,
                "admission": "desired_intersect_provider_confirmed_current_connection",
                "checked_at": "after_fresh_position_query_before_entry_dispatch",
                "failure": "block_entries_retry_next_tick_preserve_exits",
                "partial": "unconfirmed_non_critical_symbols_excluded_individually",
                "required_confirmed": "critical_and_held_symbols_else_block_all_entries",
                "provider_symbol_limit": "refused_symbols_dropped_from_desired_never_replayed_not_resent_until_capacity_freed",
                "protected_request": "benchmarks_and_held_requested_first_on_their_own_never_skipped_as_refused",
                "new_symbols": "wait_for_actual_bars_no_REST_prefill",
                "global_staleness_policy": "aggregate_stream_loss_or_critical_symbol_stale_blocks_entries",
                "per_symbol_staleness_policy": "stale_or_unadmitted_symbol_rejected_by_shared_entry_gate",
            },
            # Audit 2026-09-30 safety release (EXE-05, EXE-06, OPS-04, CFG-01).
            "broker_position_reads": {
                "failed_read": "unknown_never_flat",
                "tick_on_unknown": "block_entries_skip_reconcile_no_exit_flatten_or_overnight_action_from_stale_snapshot",
                "subscriptions_on_unknown": "held_names_from_last_confirmed_snapshot_stay_subscribed",
                "exit_call_on_unknown": "reread_once_then_hold_any_side_exit",
                "startup_on_unknown": "keep_entry_metadata_skip_reconstruction",
                "post_close_on_unknown": "last_confirmed_snapshot_else_critical_flatness_unverified",
                "critical_after_consecutive_ticks": OrganismLiveEngine._POSITIONS_UNKNOWN_CRITICAL_TICKS,
            },
            "eod_session": {
                "close_source": "nyse_calendar_market_close_time",
                "late_entry_block_minutes_before_close": _engine_module.EOD_LATE_ENTRY_BLOCK_MINUTES,
                "flatten_minutes_before_close": _engine_module.EOD_FLATTEN_WINDOW_MINUTES,
                "overnight_forced_exit_window": "09:30_until_flatten_window_start",
                "post_close_escalation": "at_or_after_close",
            },
            "daily_loss_baseline": {
                "persisted_keys": ["daily_loss_session_date", "daily_starting_equity",
                                   "daily_loss_halt", "daily_loss_halt_session"],
                "restart": "same_session_restores_baseline_and_halt_no_roll_reapplies_governance_halt",
                "earlier_session_halt": "carried_over_and_cleared_on_the_new_session_first_tick",
                "missing_baseline": "rebaseline_at_current_equity_critical_after_the_open",
                "write": "brain_save_and_immediate_atomic_write_on_roll_or_halt",
            },
            # Audit 2026-10-05 C01-01: exit guard in the outbox dispatch path.
            "order_dispatch_guards": {
                "exit_sell": "client_key_lookup_then_broker_position_refuse_if_free_long_below_order_qty",
                "exit_free_long_source": "qty_available_else_qty_zero_when_flat_or_short",
                "exit_scope": "declared_exit_or_close_position_or_undeclared_sell_when_long_only",
                "exit_size_policy": "refuse_not_clamp",
                "buy_to_cover": "not_checked",
                "entries": "no_exit_guard_reads_age_and_session_limits_in_outbox_worker_see_order_dead_letter_lifecycle",
                "refused_order_status": _outbox_dispatch.REFUSED_ORDER_STATUS,
                "refusal_reasons": [
                    "exit_position_flat", "exit_position_short",
                    "exit_exceeds_free_long_position", "broker_rejected_insufficient_qty",
                ],
                "broker_insufficient_qty": "terminal_rejected_never_retried",
                "found_at_broker_by_client_key": "attached_never_resent",
                "failed_guard_read": "not_sent_event_retried",
                "refusal_record": "order_attributes_dispatch_refusal_and_event_dead_lettered_in_one_transaction",
                "page": "critical_after_commit_duplicate_flat_exit_has_its_own_headline",
            },
            # Audit 2026-10-05 C01-04 / C04-01: entry dispatch limits and the
            # dead-letter lifecycle (outbox worker, not frozen surface).
            "order_dead_letter_lifecycle": {
                "entry_dispatch_max_age_seconds": _outbox_worker.ENTRY_DISPATCH_MAX_AGE_SECONDS,
                "entry_age_basis": "outbox_event_created_at_intent_time_unchanged_by_retries",
                "entry_session_rule": "created_in_a_regular_nyse_session_refused_once_that_session_closed_early_closes_included",
                "entry_scope": "every_order_except_exits_and_lookup_only_events",
                "entry_refusal": "dead_lettered_without_dispatch_attempt_notice_order_expired_warning_no_page",
                "entry_check_failure": "held_and_retried_never_sent_unchecked",
                "record": "orders_attributes_outbox_dead_letter_in_the_dead_letter_transaction_unambiguous_unsent_rows_only",
                "settle_seconds": _outbox_worker.DEAD_LETTER_SETTLE_SECONDS,
                "sweep_interval_seconds": _outbox_worker.DEAD_LETTER_SWEEP_SECONDS,
                "lookup_timeout_seconds": _outbox_worker.DEAD_LETTER_LOOKUP_TIMEOUT_SECONDS,
                "lookups_per_sweep": _outbox_worker.DEAD_LETTER_SWEEP_BATCH,
                "candidates_per_sweep": _outbox_worker.DEAD_LETTER_CANDIDATE_LIMIT,
                "pending_event_scan_limit": _outbox_worker.DEAD_LETTER_PENDING_SCAN_LIMIT,
                "retry_backoff": "doubling_from_sweep_interval_in_memory",
                "max_backoff_seconds": _outbox_worker.DEAD_LETTER_MAX_BACKOFF_SECONDS,
                "absence": "definitive_404_for_persisted_client_key_after_commit_and_settle_with_no_other_pending_event",
                "finalized_status": _outbox_worker.DEAD_LETTER_ORDER_STATUS,
                "refused_entry_finalized_status": _outbox_worker.EXPIRED_ENTRY_ORDER_STATUS,
                "finalize_recheck": "row_lock_unsent_row_and_event_still_dead_lettered",
                "found_at_broker": "attached_by_client_key_through_acknowledgement_path_critical",
                "unknown": "retried_never_finalized",
                "ambiguous_dead_letters": "not_recorded_unchanged_handling",
                "dead_lettered_sells": "finalized_the_same_way_exe04_critical_unchanged",
            },
            # Audit 2026-10-05 C08-01: which unresolved or replaced orders hold an
            # identified lifetime's exact close accounting (policy id unchanged).
            "close_accounting_holds": {
                "session_bounded_tifs": sorted(_fill_lookup.SESSION_BOUNDED_TIFS),
                "session_cutoff_slack_seconds": int(_fill_lookup.SESSION_CUTOFF_SLACK.total_seconds()),
                "session_end_slack_seconds": int(_fill_lookup.SESSION_END_SLACK.total_seconds()),
                "session_search_days": _fill_lookup._SESSION_SEARCH_DAYS,
                "session_end": "20:00_et_of_first_nyse_trading_day_whose_regular_close_is_after_basis_plus_cutoff_slack",
                "acknowledged_basis": "max(submitted_at, updated_at)",
                "unacknowledged_basis": "submitted_at",
                "unacknowledged_limit": "ambiguous_submission_without_persisted_broker_id_untracked_flat_to_flat_backstop",
                "gtc_or_unknown_tif": "hold_until_terminal",
                "in_lifetime": "always_hold",
                "late_pre_entry_fill": "hold_unbounded",
                "replaced_day_predecessor": "session_bounded_assumes_successor_kept_session_bounded_tif",
                "hold_reason": "ambiguous_order:<id>|replacement_lineage_unverified",
                "hold_warning": "once_per_new_reason_cleared_on_resolution",
                "zero_fill_cleanup_scan": "orders_submitted_from_entry_to_pending_close_observed_at_else_unbounded",
            },
            # Audit 2026-10-05 C07-01: lot-ledger effects of broker-confirmed fills.
            "fill_lot_accounting": {
                "unmatched_close": "persist_summary_execution_and_matched_lots_record_attributes.lot_accounting",
                "lot_matching": "owner_scoped_fifo",
                "deferral": "close_retryable_while_same_owner_opening_in_recovery_scope_unresolved",
                "deferral_window": "opening_submitted_at_or_before_close_and_at_most_grace_before_it",
                "lot_ordering_grace_seconds": int(_fill_ingestion.LOT_ORDERING_GRACE.total_seconds()),
                "lot_ordering_max_age_seconds": int(_fill_ingestion.LOT_ORDERING_MAX_AGE.total_seconds()),
                "late_netting": "new_opening_lot_closes_owner_unmatched_closes_submitted_at_or_after_it_within_grace_fifo",
                "late_match_price": "close_unmatched_vwap",
                "record_statuses": ["unmatched", "matched_late"],
                "record_decimal_places": 6,
                "ordering_basis": "submission_time_not_broker_fill_time",
                "page": "critical_after_commit_all_five_ingress",
                "late_match_log": "warning_after_commit_all_five_ingress",
                "startup_page_order": "oldest_first_after_persisted_order_recovery",
                "transient_failure": "whole_order_rolled_back_and_retried",
            },
            "runtime_config_hash_env": list(_runtime_identity.RUNTIME_HASH_ENV),
            "entry_freshness": {
                "required_timeframe": ENTRY_TIMEFRAME,
                "max_bar_age_seconds": MAX_ENTRY_BAR_AGE_SECONDS,
                "minimum_bar_age_seconds": 0.0,
                "timestamp_semantics": "provider_bar_start_utc",
                "checked_at": "final_entry_submission",
                "missing_or_invalid_timestamp": "reject_entry",
                "protective_exits_exempt": True,
            },
            "research_policy": policy_status(),
            "timeframe": LIVE_TIMEFRAME,
            "lookback": LIVE_LOOKBACK,
            "min_bars": MIN_BARS,
            "prediction_horizon": PREDICTION_HORIZON,
            "tick_interval_seconds": 10,
            "universe": [s.strip() for s in LIVE_UNIVERSE_CSV.split(",") if s.strip()],
            "universe_size": len([s for s in LIVE_UNIVERSE_CSV.split(",") if s.strip()]),

            "learning_mode_threshold_trades": ML_ISOLATION_TRADES,
            "evolution_freeze_until_trades": EVOLUTION_FREEZE_TRADES,
            "production_promotion_gate": {
                "min_total_pnl": PROMOTION_MIN_TOTAL_PNL,
                "min_last_50_mean_pnl": PROMOTION_MIN_LAST_50_MEAN_PNL,
                "min_last_50_win_rate": PROMOTION_MIN_LAST_50_WIN_RATE,
                "min_sharpe_per_trade": PROMOTION_MIN_SHARPE_PER_TRADE,
            },

            "max_positions": MAX_OPEN_POSITIONS,
            "alpha_top_n": ALPHA_TOP_N,
            "long_only": LONG_ONLY,

            "exploration_enabled": EXPLORATION_ENABLED,
            "alpha_breakout_bad_regime_filter_enabled": (
                ALPHA_BREAKOUT_BAD_REGIME_FILTER_ENABLED
            ),
            "candidate_filter_shadow_telemetry_enabled": (
                CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED
            ),
            "candidate_filter_shadow_telemetry_path": (
                CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH
            ),
            "strategy_evidence_telemetry_enabled": (
                STRATEGY_EVIDENCE_TELEMETRY_ENABLED
            ),
            "strategy_evidence_telemetry_path": (
                STRATEGY_EVIDENCE_TELEMETRY_PATH
            ),
            "phase9_shadow_engines_enabled": PHASE9_SHADOW_ENGINES_ENABLED,
            "streaming_enabled": USE_STREAMING,
            "retrain_interval": RETRAIN_INTERVAL,

            "drawdown_kill_pct": DEFAULT_DRAWDOWN_KILL_PCT,
            "drawdown_cooldown_s": DEFAULT_DRAWDOWN_COOLDOWN_S,
            "max_changes_per_day": DEFAULT_MAX_CHANGES_PER_DAY,
            "max_notional_per_trade": MAX_NOTIONAL_PER_TRADE,
            "max_daily_loss": MAX_DAILY_LOSS,

            "confidence_gate_baseline": 0.40,
            "confidence_gate_defensive": 0.45,
            "fitness_gate_production": 0.45,
            "fitness_gate_learning": 0.0,

            "risk_budget_production": KellySizer._RISK_BUDGET_PER_TRADE,
            "risk_budget_learning": KellySizer._RISK_BUDGET_PER_TRADE_LEARNING,
            "risk_budget_guarded": KellySizer._RISK_BUDGET_PER_TRADE_LEARNING,
            "risk_budget_stop_atr": KellySizer._RISK_BUDGET_STOP_ATR,

            "stop_atr_table": AdaptiveExitEngine.REGIME_STOP_ATR,
            "tp_r_table": AdaptiveExitEngine.REGIME_TP_R,
            "trail_atr_table": AdaptiveExitEngine.REGIME_TRAIL_ATR,
            "max_bars_table": AdaptiveExitEngine.REGIME_MAX_BARS,

            "horizon_timeout_bars": 18,
            "bar_boundary_entry_only": True,

            "inverse_etfs": sorted(AlphaScanner.INVERSE_ETFS),
            "inverse_etf_enabled": True,

            "confidence_weights_learning": {
                "breakout": 0.65, "tension": 0.35, "ml": 0.0,
            },
            "confidence_weights_guarded": {
                "breakout": 0.65, "tension": 0.35, "ml": 0.0,
            },
            "confidence_weights_production": {
                "ml": 0.50, "breakout": 0.30, "tension": 0.20,
            },
        }

    except Exception as e:  # noqa: BLE001
        return {
            "source": "env_fallback",
            "error": str(e),
            "timeframe": os.getenv("ORGANISM_LIVE_TIMEFRAME", "1Min"),
            "tick_interval_seconds": int(os.getenv("ORGANISM_TICK_INTERVAL_SECONDS", "10")),
            "max_positions": int(os.getenv("ORGANISM_MAX_POSITIONS", "8")),
            "drawdown_kill_pct": float(os.getenv("ORGANISM_DRAWDOWN_KILL_PCT", "0.05")),
            "drawdown_cooldown_s": int(os.getenv("ORGANISM_DRAWDOWN_COOLDOWN_S", "3600")),
            "max_changes_per_day": int(os.getenv("ORGANISM_MAX_CHANGES_PER_DAY", "100")),
            "max_notional_per_trade": float(os.getenv("ORGANISM_MAX_NOTIONAL", "0")),
            "max_daily_loss": float(os.getenv("ORGANISM_MAX_DAILY_LOSS", "0")),
            "alpha_breakout_bad_regime_filter_enabled": (
                os.getenv(
                    "ORGANISM_ALPHA_BREAKOUT_BAD_REGIME_FILTER_ENABLED",
                    "true",
                ).lower()
                in ("1", "true", "yes")
            ),
            "candidate_filter_shadow_telemetry_enabled": (
                os.getenv(
                    "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED",
                    "false",
                ).lower()
                in ("1", "true", "yes")
            ),
            "candidate_filter_shadow_telemetry_path": os.getenv(
                "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH",
                "organism_brain/candidate_filter_shadow_telemetry.jsonl",
            ),
            "strategy_evidence_telemetry_enabled": (
                os.getenv(
                    "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED",
                    "false",
                ).lower()
                in ("1", "true", "yes")
            ),
            "strategy_evidence_telemetry_path": os.getenv(
                "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH",
                "organism_brain/strategy_evidence_events.jsonl",
            ),
            "phase9_shadow_engines_enabled": (
                os.getenv(
                    "ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED",
                    "false",
                ).lower()
                in ("1", "true", "yes")
            ),
            "learning_mode_threshold_trades": 200,
            "evolution_freeze_until_trades": 300,
            "production_promotion_gate": {
                "min_total_pnl": 0.0,
                "min_last_50_mean_pnl": 0.0,
                "min_last_50_win_rate": 0.35,
                "min_sharpe_per_trade": 0.0,
            },
            "alpha_top_n": 5,
            "horizon_timeout_bars": 18,
            "bar_boundary_entry_only": True,
        }


def _configuration_evidence_scope(resolved: dict) -> str:
    """Describe configuration inputs without claiming observed engine values."""
    if resolved.get("container_env"):
        return "container_configuration_resolution_not_engine_observation"
    if resolved.get("dotenv"):
        return "local_dotenv_configuration_resolution_not_runtime_observation"
    return "offline_source_and_process_defaults_not_runtime_observation"


def _build_resolved_config_snapshot() -> dict:
    """Build resolved config snapshot: container env > .env > code defaults.

    This captures the CONFIG RESOLUTION chain (what the process SHOULD run with),
    not what it IS running with. For the live process state, see
    _build_live_process_snapshot().
    """
    resolved = {"source": "resolved_config"}

    # --- Container env vars ---
    api_container = _find_api_container()
    container_env = {}
    if api_container:
        env_text = _docker_exec(api_container, "env")
        if env_text:
            env_map = _parse_env_text(env_text)
            resolved["container"] = api_container
            container_env = {
                "ORGANISM_DRAWDOWN_KILL_PCT": env_map.get("ORGANISM_DRAWDOWN_KILL_PCT"),
                "ORGANISM_DRAWDOWN_COOLDOWN_S": env_map.get("ORGANISM_DRAWDOWN_COOLDOWN_S"),
                "ORGANISM_MAX_CHANGES_PER_DAY": env_map.get("ORGANISM_MAX_CHANGES_PER_DAY"),
                "ORGANISM_MAX_POSITIONS": env_map.get("ORGANISM_MAX_POSITIONS"),
                "ORGANISM_MAX_DAILY_LOSS": env_map.get("ORGANISM_MAX_DAILY_LOSS"),
                "ORGANISM_MAX_NOTIONAL": env_map.get("ORGANISM_MAX_NOTIONAL"),
                "ORGANISM_TICK_INTERVAL_SECONDS": env_map.get("ORGANISM_TICK_INTERVAL_SECONDS"),
                "ORGANISM_APPROVED_POLICY_BASELINE": env_map.get("ORGANISM_APPROVED_POLICY_BASELINE"),
                "ORGANISM_EXPLORATION_ENABLED": env_map.get("ORGANISM_EXPLORATION_ENABLED"),
                "ORGANISM_ALPHA_BREAKOUT_BAD_REGIME_FILTER_ENABLED": env_map.get(
                    "ORGANISM_ALPHA_BREAKOUT_BAD_REGIME_FILTER_ENABLED"
                ),
                "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED": env_map.get(
                    "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED"
                ),
                "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH": env_map.get(
                    "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH"
                ),
                "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED": env_map.get(
                    "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED"
                ),
                "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH": env_map.get(
                    "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH"
                ),
                "ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED": env_map.get(
                    "ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED"
                ),
                "ORGANISM_ALPHA_TOP_N": env_map.get("ORGANISM_ALPHA_TOP_N"),
                "ORGANISM_LIVE_TIMEFRAME": env_map.get("ORGANISM_LIVE_TIMEFRAME"),
                "APP_ENVIRONMENT": env_map.get("APP_ENVIRONMENT"),
                "ALPACA_PAPER": env_map.get("ALPACA_PAPER"),
                "ORGANISM_OPERATOR_CONTROL_STATE": env_map.get("ORGANISM_OPERATOR_CONTROL_STATE"),
            }
            resolved["container_env"] = container_env

    # --- .env file vars ---
    dotenv = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        env_map = _parse_env_file(env_file)
        dotenv = {
            "ORGANISM_DRAWDOWN_KILL_PCT": env_map.get("ORGANISM_DRAWDOWN_KILL_PCT"),
            "ORGANISM_DRAWDOWN_COOLDOWN_S": env_map.get("ORGANISM_DRAWDOWN_COOLDOWN_S"),
            "ORGANISM_MAX_CHANGES_PER_DAY": env_map.get("ORGANISM_MAX_CHANGES_PER_DAY"),
            "ORGANISM_MAX_POSITIONS": env_map.get("ORGANISM_MAX_POSITIONS"),
            "ORGANISM_MAX_DAILY_LOSS": env_map.get("ORGANISM_MAX_DAILY_LOSS"),
            "ORGANISM_MAX_NOTIONAL": env_map.get("ORGANISM_MAX_NOTIONAL"),
            "ORGANISM_TICK_INTERVAL_SECONDS": env_map.get("ORGANISM_TICK_INTERVAL_SECONDS"),
            "ORGANISM_EXPLORATION_ENABLED": env_map.get("ORGANISM_EXPLORATION_ENABLED"),
            "ORGANISM_ALPHA_BREAKOUT_BAD_REGIME_FILTER_ENABLED": env_map.get(
                "ORGANISM_ALPHA_BREAKOUT_BAD_REGIME_FILTER_ENABLED"
            ),
            "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED": env_map.get(
                "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED"
            ),
            "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH": env_map.get(
                "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH"
            ),
            "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED": env_map.get(
                "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED"
            ),
            "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH": env_map.get(
                "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH"
            ),
            "ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED": env_map.get(
                "ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED"
            ),
            "ORGANISM_ALPHA_TOP_N": env_map.get("ORGANISM_ALPHA_TOP_N"),
        }
        resolved["dotenv"] = dotenv

    # --- Resolve: container env > .env > code defaults ---
    defaults = _build_defaults_snapshot()

    resolution_sources: dict[str, str] = {}

    def _resolve_float(env_key: str, default_key: str, output_key: str) -> float:
        for label, src in [("container_env", container_env), ("dotenv", dotenv)]:
            v = src.get(env_key)
            if v not in (None, ""):
                try:
                    resolution_sources[output_key] = label
                    return float(v)
                except (ValueError, TypeError):
                    pass
        resolution_sources[output_key] = "code_default"
        return defaults.get(default_key, 0.0)

    def _resolve_int(env_key: str, default_key: str, output_key: str) -> int:
        for label, src in [("container_env", container_env), ("dotenv", dotenv)]:
            v = src.get(env_key)
            if v not in (None, ""):
                try:
                    resolution_sources[output_key] = label
                    return int(v)
                except (ValueError, TypeError):
                    pass
        resolution_sources[output_key] = "code_default"
        return defaults.get(default_key, 0)

    def _resolve_bool(env_key: str, default_key: str, output_key: str) -> bool:
        for label, src in [("container_env", container_env), ("dotenv", dotenv)]:
            v = src.get(env_key)
            if v not in (None, ""):
                resolution_sources[output_key] = label
                return v.lower() in ("true", "1", "yes")
        resolution_sources[output_key] = "code_default"
        return defaults.get(default_key, False)

    def _resolve_str(env_key: str, default_key: str) -> tuple[str, str]:
        """Resolve a string config. Returns (value, source)."""
        for label, src in [("container_env", container_env), ("dotenv", dotenv)]:
            v = src.get(env_key)
            if v not in (None, ""):
                return v, label
        return defaults.get(default_key, ""), "code_default"

    timeframe_val, timeframe_source = _resolve_str("ORGANISM_LIVE_TIMEFRAME", "timeframe")
    resolution_sources["timeframe"] = timeframe_source
    shadow_path_val, shadow_path_source = _resolve_str(
        "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH",
        "candidate_filter_shadow_telemetry_path",
    )
    resolution_sources["candidate_filter_shadow_telemetry_path"] = (
        shadow_path_source
    )
    evidence_path_val, evidence_path_source = _resolve_str(
        "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH",
        "strategy_evidence_telemetry_path",
    )
    resolution_sources["strategy_evidence_telemetry_path"] = (
        evidence_path_source
    )

    resolved["resolved"] = {
        # This describes the checked-out candidate. Only live status below
        # establishes which accounting policy the installed process runs.
        "close_accounting_policy": defaults.get("close_accounting_policy"),
        "candidate_data_pipeline_sources": defaults.get("candidate_data_pipeline_sources"),
        "composite_feature_columns": defaults.get("composite_feature_columns"),
        "streaming_subscription_sync": defaults.get("streaming_subscription_sync"),
        "pending_entry_resolution": defaults.get("pending_entry_resolution"),
        "broker_position_reads": defaults.get("broker_position_reads"),
        "eod_session": defaults.get("eod_session"),
        "daily_loss_baseline": defaults.get("daily_loss_baseline"),
        "order_dispatch_guards": defaults.get("order_dispatch_guards"),
        "order_dead_letter_lifecycle": defaults.get("order_dead_letter_lifecycle"),
        "close_accounting_holds": defaults.get("close_accounting_holds"),
        "fill_lot_accounting": defaults.get("fill_lot_accounting"),
        "runtime_config_hash_env": defaults.get("runtime_config_hash_env"),
        "entry_freshness": defaults.get("entry_freshness"),
        "drawdown_kill_pct": _resolve_float(
            "ORGANISM_DRAWDOWN_KILL_PCT", "drawdown_kill_pct", "drawdown_kill_pct",
        ),
        "drawdown_cooldown_s": _resolve_int(
            "ORGANISM_DRAWDOWN_COOLDOWN_S", "drawdown_cooldown_s", "drawdown_cooldown_s",
        ),
        "max_changes_per_day": _resolve_int(
            "ORGANISM_MAX_CHANGES_PER_DAY", "max_changes_per_day", "max_changes_per_day",
        ),
        "max_positions": _resolve_int(
            "ORGANISM_MAX_POSITIONS", "max_positions", "max_positions",
        ),
        "max_daily_loss": _resolve_float(
            "ORGANISM_MAX_DAILY_LOSS", "max_daily_loss", "max_daily_loss",
        ),
        "max_notional_per_trade": _resolve_float(
            "ORGANISM_MAX_NOTIONAL", "max_notional_per_trade", "max_notional_per_trade",
        ),
        "alpha_top_n": _resolve_int("ORGANISM_ALPHA_TOP_N", "alpha_top_n", "alpha_top_n"),
        "tick_interval_seconds": _resolve_int(
            "ORGANISM_TICK_INTERVAL_SECONDS", "tick_interval_seconds", "tick_interval_seconds",
        ),
        "exploration_enabled": _resolve_bool(
            "ORGANISM_EXPLORATION_ENABLED", "exploration_enabled", "exploration_enabled",
        ),
        "alpha_breakout_bad_regime_filter_enabled": _resolve_bool(
            "ORGANISM_ALPHA_BREAKOUT_BAD_REGIME_FILTER_ENABLED",
            "alpha_breakout_bad_regime_filter_enabled",
            "alpha_breakout_bad_regime_filter_enabled",
        ),
        "candidate_filter_shadow_telemetry_enabled": _resolve_bool(
            "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED",
            "candidate_filter_shadow_telemetry_enabled",
            "candidate_filter_shadow_telemetry_enabled",
        ),
        "candidate_filter_shadow_telemetry_path": shadow_path_val,
        "strategy_evidence_telemetry_enabled": _resolve_bool(
            "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED",
            "strategy_evidence_telemetry_enabled",
            "strategy_evidence_telemetry_enabled",
        ),
        "strategy_evidence_telemetry_path": evidence_path_val,
        "phase9_shadow_engines_enabled": _resolve_bool(
            "ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED",
            "phase9_shadow_engines_enabled",
            "phase9_shadow_engines_enabled",
        ),
        "timeframe": timeframe_val,
        "timeframe_source": timeframe_source,
        "learning_mode_threshold_trades": defaults.get("learning_mode_threshold_trades"),
        "evolution_freeze_until_trades": defaults.get("evolution_freeze_until_trades"),
        "production_promotion_gate": defaults.get("production_promotion_gate"),
        "research_policy": defaults.get("research_policy"),
        "horizon_timeout_bars": defaults.get("horizon_timeout_bars"),
        "bar_boundary_entry_only": defaults.get("bar_boundary_entry_only"),
        "confidence_gate_baseline": defaults.get("confidence_gate_baseline"),
        "confidence_gate_defensive": defaults.get("confidence_gate_defensive"),
        "fitness_gate_production": defaults.get("fitness_gate_production"),
        "risk_budget_learning": defaults.get("risk_budget_learning"),
        "risk_budget_guarded": defaults.get("risk_budget_guarded"),
        "risk_budget_production": defaults.get("risk_budget_production"),
        "inverse_etfs": defaults.get("inverse_etfs"),
        "universe_size": defaults.get("universe_size"),
        "confidence_weights_learning": defaults.get("confidence_weights_learning"),
        "confidence_weights_guarded": defaults.get("confidence_weights_guarded"),
        "confidence_weights_production": defaults.get("confidence_weights_production"),
        "stop_atr_table": defaults.get("stop_atr_table"),
    }
    resolved["resolution_sources"] = resolution_sources
    resolved["evidence_scope"] = _configuration_evidence_scope(resolved)
    resolved["engine_observed"] = False

    return resolved


def _build_legacy_runtime_snapshot(
    defaults: dict,
    resolved: dict,
    live_process: dict,
) -> dict:
    """Build the flat legacy snapshot used by older CI consumers.

    Historically ``runtime_config_snapshot.json`` contained code defaults,
    which made operator-facing artifacts disagree with the running paper
    container whenever env overrides were active. Keep the flat shape, but
    populate it from the resolved config chain.
    """
    container_env = resolved.get("container_env") or {}
    flat = dict(resolved.get("resolved") or {})
    flat.update({
        "source": "resolved_config",
        "snapshot_source": "resolved_config_snapshot",
        "evidence_scope": _configuration_evidence_scope(resolved),
        "engine_observed": False,
        "container": resolved.get("container"),
        "app_environment": container_env.get("APP_ENVIRONMENT"),
        "alpaca_paper": container_env.get("ALPACA_PAPER"),
        "resolution_sources": resolved.get("resolution_sources") or {},
        "code_defaults": {
            "drawdown_kill_pct": defaults.get("drawdown_kill_pct"),
            "drawdown_cooldown_s": defaults.get("drawdown_cooldown_s"),
            "max_changes_per_day": defaults.get("max_changes_per_day"),
            "max_positions": defaults.get("max_positions"),
            "max_daily_loss": defaults.get("max_daily_loss"),
            "max_notional_per_trade": defaults.get("max_notional_per_trade"),
            "production_promotion_gate": defaults.get("production_promotion_gate"),
            "risk_budget_guarded": defaults.get("risk_budget_guarded"),
            "confidence_weights_guarded": defaults.get("confidence_weights_guarded"),
        },
        "live_process_reachable": live_process.get("reachable"),
        "config_truth_status": _assess_config_truth(resolved, live_process),
    })
    return flat


def _assess_config_truth(resolved: dict, live_process: dict) -> dict:
    """Compare resolved config with live process env evidence."""
    process_env = live_process.get("process_env") or {}
    if not process_env:
        return {
            "status": "unverified",
            "mismatches": [],
            "note": "live process env was unavailable",
        }

    checks = {
        "drawdown_kill_pct": ("ORGANISM_DRAWDOWN_KILL_PCT", float),
        "drawdown_cooldown_s": ("ORGANISM_DRAWDOWN_COOLDOWN_S", int),
        "max_changes_per_day": ("ORGANISM_MAX_CHANGES_PER_DAY", int),
        "max_positions": ("ORGANISM_MAX_POSITIONS", int),
        "max_daily_loss": ("ORGANISM_MAX_DAILY_LOSS", float),
        "max_notional_per_trade": ("ORGANISM_MAX_NOTIONAL", float),
        "tick_interval_seconds": ("ORGANISM_TICK_INTERVAL_SECONDS", int),
    }
    resolved_values = resolved.get("resolved") or {}
    mismatches = []
    for output_key, (env_key, caster) in checks.items():
        env_val = process_env.get(env_key)
        if env_val in (None, "") or output_key not in resolved_values:
            continue
        try:
            live_val = caster(env_val)
            resolved_val = caster(resolved_values[output_key])
        except (TypeError, ValueError):
            mismatches.append({
                "key": output_key,
                "resolved": resolved_values.get(output_key),
                "live_env": env_val,
                "reason": "unparseable",
            })
            continue
        if isinstance(live_val, float):
            equal = abs(live_val - resolved_val) <= 1e-9
        else:
            equal = live_val == resolved_val
        if not equal:
            mismatches.append({
                "key": output_key,
                "resolved": resolved_val,
                "live_env": live_val,
            })

    return {
        "status": "consistent" if not mismatches else "drift",
        "mismatches": mismatches,
    }


def _build_live_process_snapshot() -> dict:
    """Query the RUNNING paper-trader process for its actual live state.

    This is the only snapshot that reflects what the organism is actually
    doing right now — not what config says it should do, but what it IS doing.

    Sources (in priority order):
    1. /api/organism/status endpoint (running process memory)
    2. Docker exec: read process-level state files (brain gen, trade count)
    3. Container env as fallback context
    """
    from datetime import datetime, timezone

    api_container = _find_api_container()
    snapshot_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    result = {
        "source": "live_process",
        "snapshot_taken_at": snapshot_ts,
        "container": api_container or None,
        "reachable": False,
        "organism_status": None,
        "brain_state": None,
        "process_env": None,
        "source_annotations": {},
    }

    # --- 1. Query organism status endpoint (live process memory) ---
    status_json = _curl_organism_status()
    if status_json:
        result["reachable"] = True
        result["organism_status"] = status_json
    else:
        result["reachable"] = False
        result["unreachable_reason"] = (
            "organism status endpoint returned no data or is not responding"
        )

    # --- 2. Read brain state from container filesystem ---
    if api_container:
        # Read brain manifest if accessible
        brain_meta = _docker_exec(
            api_container,
            "cat /app/organism_brain/manifest.json",
        )
        if brain_meta:
            try:
                result["brain_state"] = json.loads(brain_meta)
            except (json.JSONDecodeError, ValueError):
                result["brain_state"] = {"raw": brain_meta[:500]}

        # Read process env for context
        env_text = _docker_exec(api_container, "env")
        if env_text:
            env_map = _parse_env_text(env_text)
            result["process_env"] = {
                "GIT_SHA": env_map.get("GIT_SHA"),
                "BUILD_TIME": env_map.get("BUILD_TIME"),
                "IMAGE_SHA": env_map.get("IMAGE_SHA"),
                "APP_ENVIRONMENT": env_map.get("APP_ENVIRONMENT"),
                "ALPACA_PAPER": env_map.get("ALPACA_PAPER"),
                "ORGANISM_APPROVED_POLICY_BASELINE": env_map.get("ORGANISM_APPROVED_POLICY_BASELINE"),
                "ORGANISM_OPERATOR_CONTROL_STATE": env_map.get("ORGANISM_OPERATOR_CONTROL_STATE"),
                "ORGANISM_DRAWDOWN_KILL_PCT": env_map.get("ORGANISM_DRAWDOWN_KILL_PCT"),
                "ORGANISM_DRAWDOWN_COOLDOWN_S": env_map.get("ORGANISM_DRAWDOWN_COOLDOWN_S"),
                "ORGANISM_MAX_CHANGES_PER_DAY": env_map.get("ORGANISM_MAX_CHANGES_PER_DAY"),
                "ORGANISM_MAX_POSITIONS": env_map.get("ORGANISM_MAX_POSITIONS"),
                "ORGANISM_MAX_DAILY_LOSS": env_map.get("ORGANISM_MAX_DAILY_LOSS"),
                "ORGANISM_MAX_NOTIONAL": env_map.get("ORGANISM_MAX_NOTIONAL"),
                "ORGANISM_TICK_INTERVAL_SECONDS": env_map.get("ORGANISM_TICK_INTERVAL_SECONDS"),
                "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED": env_map.get(
                    "ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED"
                ),
                "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED": env_map.get(
                    "ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED"
                ),
                "ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED": env_map.get(
                    "ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED"
                ),
            }

        # Get container start time
        try:
            started = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.State.StartedAt}}", api_container],
                text=True, stderr=subprocess.DEVNULL, timeout=5,
            ).strip()
            result["container_started_at"] = started
        except Exception:  # noqa: BLE001, S110
            pass

    # --- 3. Derive live runtime values from process state ---
    live = {}
    annotations = {}
    if status_json:
        # The response may have nested data under live_engine.engine
        engine = {}
        le = status_json.get("live_engine", {})
        if isinstance(le, dict):
            engine = le.get("engine", {})

        def _pick_annotated(field_name: str, *keys):
            """Pick first non-None value, track where it came from."""
            for k in keys:
                for src_label, src in [("api_top_level", status_json), ("engine_memory", engine)]:
                    v = src.get(k)
                    if v is not None:
                        annotations[field_name] = f"{src_label}.{k}"
                        return v
            return None

        live["tick_count"] = _pick_annotated("tick_count", "tick_count")
        live["trade_count"] = _pick_annotated("trade_count", "total_trades", "trade_count")
        live["open_positions"] = _pick_annotated(
            "open_positions", "positions_tracked", "open_positions", "num_positions",
        )
        live["is_learning_mode"] = _pick_annotated(
            "is_learning_mode", "learning_mode", "is_learning_mode",
        )
        live["trading_phase"] = _pick_annotated("trading_phase", "trading_phase")
        live["guarded_mode"] = _pick_annotated("guarded_mode", "guarded_mode")
        live["ml_influence_enabled"] = _pick_annotated(
            "ml_influence_enabled", "ml_influence_enabled",
        )
        live["fixed_risk_sizing"] = _pick_annotated(
            "fixed_risk_sizing", "fixed_risk_sizing",
        )
        live["promotion_blockers"] = _pick_annotated(
            "promotion_blockers", "promotion_blockers",
        )
        live["close_accounting"] = _pick_annotated(
            "close_accounting", "close_accounting",
        )
        live["research_policy"] = _pick_annotated(
            "research_policy", "policy_lock",
        )
        # Report actual in-memory authority; absent legacy fields stay unknown.
        live["operator_governance"] = _pick_annotated(
            "operator_governance", "governance",
        )
        live["brain_generation"] = _pick_annotated("brain_generation", "brain_generation")
        live["uptime_seconds"] = _pick_annotated("uptime_seconds", "uptime_seconds")
        live["last_tick_at"] = _pick_annotated("last_tick_at", "last_tick", "last_tick_at")

        # Regime: flatten nested dict, explain empty/idle state
        raw_regime = _pick_annotated("regime", "regime", "current_regime")
        if isinstance(raw_regime, dict):
            regime_val = raw_regime.get("last_regime", "")
            annotations["regime"] = "api_top_level.regime.last_regime"
        else:
            regime_val = raw_regime
        if not regime_val or regime_val == "":
            regime_val = "idle"
            live["idle_reason"] = "market_closed_or_no_ticks_yet"
        live["regime"] = regime_val

        live["drawdown_pct"] = _pick_annotated("drawdown_pct", "drawdown_pct", "current_drawdown")
        live["equity"] = _pick_annotated("equity", "current_equity", "equity", "portfolio_value")
        live["ml_trained"] = _pick_annotated("ml_trained", "ml_trained")
        live["win_rate"] = _pick_annotated("win_rate", "win_rate")
        live["cumulative_pnl"] = _pick_annotated("cumulative_pnl", "cumulative_pnl")
        live["universe_size"] = _pick_annotated("universe_size", "universe_size")
        live["scanner_candidates_count"] = _pick_annotated(
            "scanner_candidates_count", "scanner_candidates_count", "scanner_candidates",
        )
        live["running"] = le.get("running") if le else _pick_annotated("running", "running")

    result["live"] = live
    result["source_annotations"] = annotations

    # --- 4. Coherence notes ---
    coherence_notes = []
    brain = result.get("brain_state") or {}
    brain_trades = brain.get("total_trades")
    engine_trades = live.get("trade_count")
    if brain_trades is not None and engine_trades is not None and brain_trades != engine_trades:
        coherence_notes.append(
            f"brain_state.total_trades={brain_trades} vs live.trade_count={engine_trades}: "
            "the counters can have different accounting scopes or save times. "
            "This comparison alone does not establish missing trades or unsaved activity; "
            "reconcile ledger attribution before changing either counter."
        )
    if brain.get("ml_is_trained") is not None and live.get("ml_trained") is not None:
        if brain.get("ml_is_trained") != live.get("ml_trained"):
            coherence_notes.append(
                f"brain_state.ml_is_trained={brain.get('ml_is_trained')} "
                f"vs live.ml_trained={live.get('ml_trained')}: "
                "brain manifest is stale if retrain happened after last save."
            )
    if not coherence_notes:
        coherence_notes.append("All cross-source values are consistent.")
    result["coherence_notes"] = coherence_notes

    return result


# ── helpers ──────────────────────────────────────────────────────────

def _find_api_container() -> str:
    """Find the running api container name."""
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--filter", "name=api", "--format", "{{.Names}}"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
        for line in out.splitlines():
            if "api" in line:
                return line
    except Exception:  # noqa: BLE001, S110
        pass
    return ""


def _docker_exec(container: str, cmd: str) -> str:
    try:
        return subprocess.check_output(
            ["docker", "exec", container, "sh", "-c", cmd],
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


def _curl_organism_status() -> dict | None:
    """Query the organism status endpoint, with auth."""
    import urllib.request

    base = os.getenv("ORGANISM_API_BASE", "http://localhost:8000")
    # Try authenticated first, then unauthenticated
    token = _get_auth_token(base)
    headers = {}
    if token:
        headers = {"Authorization": f"Bearer {token}"}

    for path in [
        "/api/v1/paper-monitor/organism/status",
        "/api/v1/organism/status",
        "/api/organism/status",
    ]:
        try:
            request = urllib.request.Request(f"{base}{path}", headers=headers)
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.load(response)
            if isinstance(data, dict) and "detail" not in data:
                return data
        except Exception:  # noqa: BLE001, S112
            continue
    return None


def _get_auth_token(base: str) -> str:
    """Get auth token for API access.

    V12 W89 (post-cleanup, COMP-407/408): removed dev-credential
    fallbacks that were used as the default when INTRA_API_USER /
    INTRA_API_PASSWORD were unset.  Operators must now set the env
    vars explicitly; an unset var returns an empty token, which
    makes the failure visible instead of silently authenticating as
    the dev admin user.
    """
    username = os.getenv("INTRA_API_USER", "")
    password = os.getenv("INTRA_API_PASSWORD", "")
    credential_file = os.getenv("INTRA_API_CREDENTIALS_FILE", "")
    if (not username or not password) and credential_file:
        try:
            path = Path(credential_file)
            if path.stat().st_mode & 0o077:
                return ""  # Refuse credentials readable by another local user.
            credentials = json.loads(path.read_text())
            username = credentials.get("username", "")
            password = credentials.get("password", "")
        except (OSError, ValueError, AttributeError):
            return ""
    if not username or not password:
        # Operator hasn't supplied credentials — return empty token
        # so callers see the auth failure explicitly.
        return ""
    try:
        import urllib.error
        import urllib.request
        req = urllib.request.Request(
            f"{base}/api/v1/auth/login",
            data=json.dumps({"username": username, "password": password}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("access_token", "")
    except Exception:  # noqa: BLE001
        return ""


def _parse_env_text(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _parse_env_file(path: Path) -> dict:
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            result[k.strip()] = v
    return result


# ── main ─────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Code defaults snapshot
    defaults = _build_defaults_snapshot()
    p1 = ART / "runtime_defaults_snapshot.json"
    p1.write_text(json.dumps(defaults, indent=2))
    print(f"Defaults snapshot written to {p1}")

    # 2. Resolved config snapshot (env > .env > code defaults)
    resolved = _build_resolved_config_snapshot()
    p2 = ART / "resolved_config_snapshot.json"
    p2.write_text(json.dumps(resolved, indent=2))
    print(f"Resolved config snapshot written to {p2}")

    # 3. Live process snapshot (from running container)
    live = _build_live_process_snapshot()
    p3 = ART / "live_process_runtime_snapshot.json"
    p3.write_text(json.dumps(live, indent=2))
    print(f"Live process snapshot written to {p3}")

    # 4. Backward compat: flat resolved snapshot for older CI consumers.
    p4 = ART / "runtime_config_snapshot.json"
    p4.write_text(json.dumps(_build_legacy_runtime_snapshot(defaults, resolved, live), indent=2))
    print(f"Legacy snapshot written to {p4}")


if __name__ == "__main__":
    main()
