\set ON_ERROR_STOP on

SELECT format('CREATE ROLE %I LOGIN', :'backend_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'backend_user')
\gexec
SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L',
    :'backend_user', :'backend_password'
)
\gexec

SELECT format('CREATE ROLE %I LOGIN', :'fetcher_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'fetcher_user')
\gexec
SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L',
    :'fetcher_user', :'fetcher_password'
)
\gexec

REVOKE CREATE ON SCHEMA public FROM PUBLIC;

SELECT format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I', :'backend_user')
\gexec
SELECT format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I', :'backend_user')
\gexec
SELECT format('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM %I', :'fetcher_user')
\gexec
SELECT format('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM %I', :'fetcher_user')
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'backend_user')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'backend_user')
\gexec
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', :'backend_user')
\gexec
SELECT format('GRANT INSERT (source, metadata_json) ON TABLE public.sync_states TO %I', :'backend_user')
\gexec
SELECT format('GRANT UPDATE (metadata_json, updated_at) ON TABLE public.sync_states TO %I', :'backend_user')
\gexec
SELECT format('GRANT USAGE, SELECT ON SEQUENCE public.sync_states_id_seq TO %I', :'backend_user')
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'fetcher_user')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'fetcher_user')
\gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'fetcher_user')
\gexec
SELECT format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', :'fetcher_user')
\gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON TABLES TO %I',
    :'admin_user', :'backend_user'
)
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'admin_user', :'fetcher_user'
)
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO %I',
    :'admin_user', :'fetcher_user'
)
\gexec

ALTER TABLE public.sync_states ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS backend_sync_states_select ON public.sync_states;
DROP POLICY IF EXISTS backend_manual_sync_insert ON public.sync_states;
DROP POLICY IF EXISTS backend_manual_sync_update ON public.sync_states;
DROP POLICY IF EXISTS fetcher_sync_states_all ON public.sync_states;
SELECT format(
    'CREATE POLICY backend_sync_states_select ON public.sync_states FOR SELECT TO %I USING (true)',
    :'backend_user'
)
\gexec
SELECT format(
    'CREATE POLICY backend_manual_sync_insert ON public.sync_states FOR INSERT TO %I WITH CHECK (source = %L)',
    :'backend_user', 'manual_sync'
)
\gexec
SELECT format(
    'CREATE POLICY backend_manual_sync_update ON public.sync_states FOR UPDATE TO %I USING (source = %L) WITH CHECK (source = %L)',
    :'backend_user', 'manual_sync', 'manual_sync'
)
\gexec
SELECT format(
    'CREATE POLICY fetcher_sync_states_all ON public.sync_states FOR ALL TO %I USING (true) WITH CHECK (true)',
    :'fetcher_user'
)
\gexec

SELECT 1 / (
    has_table_privilege(:'backend_user', 'public.posts', 'SELECT')
    AND NOT has_table_privilege(:'backend_user', 'public.posts', 'INSERT')
    AND has_column_privilege(:'backend_user', 'public.sync_states', 'source', 'INSERT')
    AND has_column_privilege(:'backend_user', 'public.sync_states', 'metadata_json', 'INSERT')
    AND has_column_privilege(:'backend_user', 'public.sync_states', 'metadata_json', 'UPDATE')
    AND has_column_privilege(:'backend_user', 'public.sync_states', 'updated_at', 'UPDATE')
    AND NOT has_column_privilege(:'backend_user', 'public.sync_states', 'cursor', 'UPDATE')
    AND NOT has_table_privilege(:'backend_user', 'public.sync_states', 'DELETE')
    AND has_sequence_privilege(:'backend_user', 'public.sync_states_id_seq', 'USAGE')
    AND has_table_privilege(:'fetcher_user', 'public.posts', 'SELECT')
    AND has_table_privilege(:'fetcher_user', 'public.posts', 'INSERT')
    AND has_table_privilege(:'fetcher_user', 'public.posts', 'UPDATE')
    AND has_table_privilege(:'fetcher_user', 'public.posts', 'DELETE')
    AND NOT has_schema_privilege(:'backend_user', 'public', 'CREATE')
    AND NOT has_schema_privilege(:'fetcher_user', 'public', 'CREATE')
    AND (
        SELECT count(*) = 4 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'sync_states'
          AND policyname IN (
              'backend_sync_states_select',
              'backend_manual_sync_insert',
              'backend_manual_sync_update',
              'fetcher_sync_states_all'
          )
    )
)::int AS privilege_check;
