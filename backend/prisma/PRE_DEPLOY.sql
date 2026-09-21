-- Run with DIRECT_URL before deploying the schema in this revision.
-- Back up first:
--   pg_dump "$DIRECT_URL" -n public -Fc -f pre_auth.dump

-- Confirm pgvector is installed and discoverable by the app connection.
CREATE EXTENSION IF NOT EXISTS vector;
SELECT extname, extnamespace::regnamespace::text AS schema, extversion
  FROM pg_extension WHERE extname = 'vector';
SHOW search_path;
-- If the extension is in `extensions` and that schema is absent above, add
-- options=-c%20search_path%3Dpublic%2Cextensions to DATABASE_URL and
-- DIRECT_URL (using `&options=` when the URL already has query parameters).
SELECT count(*) FROM "Agent" WHERE capability_embedding IS NOT NULL;

-- Safe only after confirming the preceding count is zero (or after accepting
-- that old 1536-dimensional embeddings will be discarded and regenerated).
ALTER TABLE "Agent" DROP COLUMN IF EXISTS capability_embedding;
ALTER TABLE "Agent" ADD COLUMN capability_embedding vector(384);
