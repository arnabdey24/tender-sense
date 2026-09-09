-- Extensions the schema depends on. Alembic also creates them (migration
-- 0001_extensions) so a database restored from a dump stays consistent.
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "citext";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
