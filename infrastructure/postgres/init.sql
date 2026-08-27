-- AEIMPS PostgreSQL initialization
-- Runs once on container first start

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Ensure the aeimps database has proper settings
ALTER DATABASE aeimps SET timezone TO 'UTC';
ALTER DATABASE aeimps SET default_text_search_config TO 'pg_catalog.english';
