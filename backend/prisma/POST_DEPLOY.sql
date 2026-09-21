-- Run after `prisma db push` has added ownership columns and cascade rules.
UPDATE "Agent"
   SET visibility = 'public', owner_id = NULL,
       published_at = COALESCE(published_at, now())
 WHERE is_system = true;

UPDATE "Agent"
   SET visibility = 'private', owner_id = NULL
 WHERE is_system = false AND owner_id IS NULL;

DELETE FROM "User" WHERE telegram_id = 'web-user-1';

-- Audit quarantined pre-auth agents; claim them manually only when ownership
-- has been independently established.
SELECT id, name, "createdAt"
  FROM "Agent"
 WHERE is_system = false AND owner_id IS NULL;
