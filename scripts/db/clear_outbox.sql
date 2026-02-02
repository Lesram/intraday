-- Clear Stuck Outbox Events
-- Run this SQL to clear the stuck orders

-- Show the stuck events first
SELECT id, topic, status, attempts, created_at
FROM outbox_events  
WHERE status = 'pending' AND attempts >= 5
ORDER BY created_at DESC;

-- Delete them
DELETE FROM outbox_events  
WHERE status = 'pending' AND attempts >= 5;

-- Verify they're gone
SELECT COUNT(*) as remaining_stuck
FROM outbox_events  
WHERE status = 'pending' AND attempts >= 5;
