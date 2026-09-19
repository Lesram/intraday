Yes — I turned this into a concrete, repo-native control-plane starter kit for Intra.

The right setup is still:

**ChatGPT / Codex = architect + reviewer**
**Claude Code = implementer + local executor**
**GitHub Actions = neutral referee**
**OpenHands = optional orchestrator later, not the source of truth**

That split matches the current product realities:

* ChatGPT’s GitHub connector is great for reading, searching, and citing repo content, but it is read-only, search-driven, and does not support searching specific filenames directly; OpenAI also notes indexing can take about 5–10 minutes. ([OpenAI Help Center][1])
* Codex can run tasks in isolated sandboxes with your repo/environment, supports automations/worktrees/git in the Codex app, and can automate code review in GitHub. OpenAI also explicitly encourages using `AGENTS.md` as persistent repo context. ([OpenAI Help Center][2])
* Claude Code supports project settings, hooks, and project-level subagents under `.claude/`, which is exactly what you want for deterministic “design → execute → verify” behavior. ([Claude API Docs][3])
* OpenHands is viable if you later want a self-hosted orchestration layer; its docs show a Docker runtime, runtime isolation, and GitHub integration. ([OpenHands Docs][4])

## I already prepared the starter kit

Download:

* [Starter kit ZIP](sandbox:/mnt/data/intra_control_plane_starter_kit.zip)
* [Unpacked starter kit folder](sandbox:/mnt/data/intra_control_plane)

It includes:

* `AGENTS.md`
* `.claude/settings.json`
* `.claude/settings.local.example.json`
* `.claude/agents/implementer.md`
* `.claude/agents/reviewer.md`
* `.claude/agents/replay-analyst.md`
* `.github/workflows/pr-verify.yml`
* `.github/workflows/paper-postclose-audit.yml`
* `.github/workflows/codex-review-trigger.yml`
* `.github/ISSUE_TEMPLATE/strategy_bug.yml`
* `.github/ISSUE_TEMPLATE/automation_task.yml`
* `scripts/ci/session_start.sh`
* `scripts/ci/pre_edit_guard.sh`
* `scripts/ci/post_edit_verify.sh`
* `scripts/ci/detect_changed_paths.py`
* `scripts/ci/write_task_report.py`
* `scripts/runtime/write_runtime_snapshot.py`
* `docs/engineering/CONTROL_PLANE.md`
* `ops/openhands/docker-compose.openhands.yml`
* `ops/openhands/README.md`

## What this starter kit does

It wires the repo into one operating loop:

**Issue / spec → Claude Code implementation → hooks → GitHub Actions verification → Codex/ChatGPT review → merge → paper deploy → post-close KPI audit → auto-reopen next task**

It also bakes our audit conclusions into hard rails:

* no live exploration trading path
* no ML influence in learning-mode main-book confidence/ranking
* no Kelly in learning mode
* no strategy-param evolution before 300 clean trades
* alpha and pure-breakout paths must share safety gates
* runtime config snapshot required for organism changes
* organism changes must run organism regression tests before merge

## What you need to do now

### 1. Copy the starter kit into the repo root

Have Claude Code apply the files from the starter kit into the Intra repo.

### 2. Rotate secrets immediately

Your uploaded `.env` contained live-looking Alpaca credentials. Rotate them now, replace tracked values with placeholders, and move real secrets to an untracked env file or secret manager.

### 3. Fix the workflow install step to match your real bootstrap command

In the uploaded backend/tests slice, I did **not** find a root `pyproject.toml`, `requirements.txt`, `pytest.ini`, `ruff.toml`, or `mypy.ini`. So the workflow currently uses a safe placeholder install block:

* install `requirements.txt` if present
* install `requirements-dev.txt` if present
* then install `pytest`

Claude Code must replace that with the repo’s real bootstrap command once it inspects the full repo root. If you use `uv`, `poetry`, a devcontainer, or a custom bootstrap script, wire that into:

* `.github/workflows/pr-verify.yml`
* `.github/workflows/paper-postclose-audit.yml`

### 4. Wire `write_runtime_snapshot.py` into the real config layer

Right now it is a stub on purpose. Claude Code must connect it to the actual live constants used by:

* `live_engine.py`
* `kelly_sizer.py`
* `adaptive_exits.py`
* `alpha_scanner.py`
* `regime.py`
* `governance.py`

The snapshot must emit the real values for:

* learning mode on/off
* drawdown kill
* `alpha_top_n`
* max positions
* confidence gates
* stop ATR table
* horizon timeout
* evolution freeze threshold
* inverse ETF enablement
* bar-boundary-only entry flag

That snapshot then becomes the thing your daily reports and `mapss.md` reference.

### 5. Enable Claude Code project behavior

Use the included:

* `.claude/settings.json`
* `.claude/agents/*`

Then create `.claude/settings.local.json` from the example and keep it uncommitted for machine-specific values.

### 6. Enable Codex review for the repo

Since Codex can review code directly in GitHub and uses `AGENTS.md` as persistent context, turn on automatic review for PRs in the repo once the control plane files are merged. ([OpenAI Help Center][2])

### 7. Start without OpenHands

Do **not** add OpenHands on day one. First stabilize the repo-native loop with:

* GitHub
* GitHub Actions
* Claude Code hooks/subagents
* Codex review

Only after that is working should you add OpenHands as an orchestrator for queued/autonomous tasks. Its Docker runtime and GitHub integration make it viable later, but it should sit on top of your existing source-of-truth workflow, not replace it. ([OpenHands Docs][4])

## The first Claude Code task queue I want you to run

After the control-plane files are merged, queue these tasks in order.

### Task 1 — Control-plane adoption

Goal: install the starter kit and make it real for this repo.

Claude Code should:

1. Copy the starter-kit files into the repo.
2. Replace placeholder test/install commands with the repo’s real bootstrap path.
3. Wire `write_runtime_snapshot.py` to actual config constants.
4. Add CI artifacts directory handling if needed.
5. Rotate `.env` handling and remove tracked secrets.
6. Open a PR with:

   * control-plane files
   * secret hygiene changes
   * runtime snapshot wiring

### Task 2 — Fix the still-broken Improve9 edges

Use the last audit findings as the acceptance criteria:

1. Remove the live exploration execution block completely.
2. Force learning-mode confidence gate to ignore ML-derived `effective_confidence`.
3. Make alpha scanner use a true `learning_mode` flag, not `ml_is_trained`, for zeroing ML.
4. Stop applying warm-start / historical evolved params during the 300-trade freeze window.
5. Restore all new `ExitLevels` fields on restart.
6. Unify alpha and pure-breakout entry gating into one shared path.
7. Separate `alpha_top_n` from `max_positions`.

### Task 3 — Test realignment

Claude Code should then update stale tests that still encode pre-Improve9 behavior, especially:

* `tests/test_organism_integration_smoke.py`
* `tests/test_algorithm_improvements.py`
* `tests/test_multi_tick_state.py`
* `tests/test_safety_invariants.py`
* `tests/test_self_evolution.py`

### Task 4 — Post-close KPI loop

Make the post-close workflow emit artifacts with:

* trades
* win rate
* avg win / avg loss
* payoff ratio
* stop-loss count and PnL
* FTF count and PnL
* horizon-timeout count and PnL
* inverse ETF activity
* realized vs predicted return ratio

Then have the workflow auto-open a GitHub issue when thresholds fail.

## The exact operating rhythm I recommend

### During the day

* ChatGPT/Codex: analyze reports + repo + mapss
* Claude Code: only patch if it is a small, reversible control fix
* Never do broad strategy surgery intraday

### Post-close

* GitHub Action runs paper-postclose-audit
* Artifacts are uploaded
* ChatGPT/Codex reviews:

  * diff
  * runtime snapshot
  * test results
  * replay / scenario artifacts
  * trading report
* If KPIs fail, open the next issue automatically

### Weekly

* one architecture pass
* one spec-vs-code drift pass
* one control-plane hygiene pass
* one strategy performance pass

## The cleanest way to phrase this to Claude Code

Use this as your first instruction after merging the starter kit:

> Implement the Intra control plane defined by `AGENTS.md`, `.claude/`, and `.github/workflows/`. Replace placeholder dependency/bootstrap commands with the repo’s real commands. Wire `scripts/runtime/write_runtime_snapshot.py` to the live organism config constants. Remove any tracked secrets from `.env` and convert secrets to placeholders. Then execute the first strategy-hardening batch: remove any live exploration execution path, force learning-mode confidence to ignore ML, make alpha scanner zero ML in learning mode based on actual learning mode rather than model training state, block startup/warm-start application of evolved params before 300 trades, restore all `ExitLevels` fields on restart, unify alpha and pure-breakout entry gates, and separate `alpha_top_n` from `max_positions`. Update stale tests to match Improve9 and produce a machine-readable task report artifact.

## My recommendation

Implement the control plane **now**, but do it in two layers:

* **Layer 1 this week:** GitHub + Actions + Claude Code hooks/subagents + Codex review
* **Layer 2 later:** optional OpenHands orchestration once Layer 1 is stable

That gets you to a streamlined, semi-autonomous engineering system without adding unnecessary orchestration risk too early.

Next moves

* Merge the starter kit into the repo and let Claude Code replace the placeholders with real bootstrap/runtime wiring.
* Rotate the leaked Alpaca credentials before anything else.
* Run the first hardening task batch against the Improve9 gaps I listed.
* After that, I’ll review the resulting PR artifacts and tighten the next loop.

[1]: https://help.openai.com/en/articles/11145903-connecting-github-to-chatgpt-deep-research-to-chatgpt-deep-research/?utm_source=chatgpt.com "Connecting GitHub to ChatGPT | OpenAI Help Center"
[2]: https://help.openai.com/en/articles/11369540/?utm_source=chatgpt.com "Using Codex with your ChatGPT plan | OpenAI Help Center"
[3]: https://docs.anthropic.com/en/docs/claude-code/hooks?utm_source=chatgpt.com "Hooks reference - Anthropic"
[4]: https://docs.all-hands.dev/openhands/usage/runtimes/docker?utm_source=chatgpt.com "Docker Runtime - OpenHands Docs"
