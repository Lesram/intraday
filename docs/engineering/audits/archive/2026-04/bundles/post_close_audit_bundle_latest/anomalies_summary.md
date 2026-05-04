# Anomalies — Apr 1, 2026 Session

## HIGH
1. **All 14 trades lost from brain**: Walk-forward gate blocked 111 saves. save_essential_state() not present in deployed container (53cc1ad). Fixed in 3534346 (deployed post-session).

## LOW
2. **C4 watchdog fired 1,927 times**: Every tick, continuously. Watchdog tick not updated on gate-blocked saves. Fixed in 3534346.
3. **"Brain saved after N fill(s)" log misleading**: Fires even when gate blocks. Creates false confidence. Not yet fixed.

## NONE / EXPECTED
4. **1 reconciliation_adjustment event**: Stale AMZN metadata from Mar 31, correctly handled.
5. **1 orphan adoption event**: AMZN partial fill adopted correctly.
