# Track III v11 — Logging Architecture (NEW LENS)

Structured vs free-text + sampling + log-level discipline + PII in logs + retention. **First-time lens; expect 2-5 findings.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`.

## Method

### 1. Structured-vs-free-text count

```
grep -rEho "logger\.(debug|info|warning|error|critical)\(" backend/ --include='*.py' | sort | uniq -c | sort -rn
```

Total log calls per level. Compare to V9 UU census (1487 handlers).

### 2. Free-text format ratio

```
grep -rEn "logger\.(error|critical|warning)\([\"']f?" backend/ --include='*.py' | wc -l  # all
grep -rEn "logger\.(error|critical|warning)\(f[\"']" backend/ --include='*.py' | wc -l  # f-string
grep -rEn "logger\.(error|critical|warning)\([\"'].*%[sdrf]" backend/ --include='*.py' | wc -l  # %-style
grep -rEn "logger\.(error|critical|warning)\(\".*\",\s*extra\s*=" backend/ --include='*.py' | wc -l  # structured
```

Document the breakdown.

### 3. PII in logs

Sample log lines that include user data:
```
grep -rEn "logger\.(info|warning|error).*username|logger\..*email|logger\..*password" backend/ --include='*.py' | head -10
```

Each = potential PII leak. Specifically:
- Login flows: do we log the email on success/failure? (Compliance-sensitive.)
- Password reset: is the new password ever logged?
- JWT contents: ever logged in full (vs first-8-chars truncated)?

### 4. Log level discipline

For each WARNING site, is it actually warning-worthy or should it be DEBUG/INFO?
For each INFO site, is it actually info-worthy or noisy DEBUG?

Sample 10 WARNING sites; tier appropriateness.

### 5. Sampling

Are high-volume log sites (per-tick logs in `_live_tick_inner`) sampled? At 1 tick / 10s, naive logging produces ~8640 lines/day per host. With 50+ logs per tick, that's 400k+ lines/day.

Look for:
```
grep -rn "if.*tick_count.*%\|sampled\|if random" backend/organism/live_engine.py | head -10
```

### 6. Retention policy

Where do logs go (file? stdout? remote)?
```
grep -rn "FileHandler\|RotatingFileHandler\|TimedRotatingFileHandler" backend/ --include='*.py' | head -5
ls logs/ 2>/dev/null | head -5
```

Disk-bounded? Rotated? Shipped to S3 / Loki / ELK?

### 7. Correlation IDs

Does each request have a `request_id` propagated through logs? Look for:
```
grep -rn "request_id\|correlation_id\|X-Request-Id" backend/ --include='*.py' | head -10
```

Without correlation IDs, tracing failed requests across modules is difficult.

### 8. Structured logger config

Is `structlog` or similar used (per memory note: "Uses logging.getLogger() NOT structlog")? If logs are JSON, what's the schema? Is it consistent?

```
grep -rn "extra=\|structlog" backend/ --include='*.py' | head -10
```

### 9. Log-driven alerting

Are there log-grep-based alerts (e.g. Loki promtail rule for "DRAWDOWN KILL SWITCH")? If yes, are they documented?

### 10. PII hash / redaction

Is there a redaction layer that scrubs PII before logs leave the process? Look for filters / formatters.

## Output

`artifacts/audit/v11_reports/track_iii_logging_architecture.md` with breakdown + findings.

Quality bar: 2-5 findings.
