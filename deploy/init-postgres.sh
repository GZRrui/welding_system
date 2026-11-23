#!/bin/sh
set -eu
export welding_app_password="$(cat /run/secrets/pg_app_password)"
export welding_migration_password="$(cat /run/secrets/pg_migration_password)"
psql -X -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv application_password welding_app_password
\getenv maintenance_password welding_migration_password
CREATE ROLE welding_app LOGIN PASSWORD :'application_password';
CREATE ROLE welding_migrate LOGIN PASSWORD :'maintenance_password';
REVOKE ALL ON DATABASE welding FROM PUBLIC;
GRANT CONNECT ON DATABASE welding TO welding_app, welding_migrate;
ALTER SCHEMA public OWNER TO welding_migrate;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO welding_app;
ALTER DEFAULT PRIVILEGES FOR ROLE welding_migrate IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO welding_app;
ALTER DEFAULT PRIVILEGES FOR ROLE welding_migrate IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO welding_app;
SQL
