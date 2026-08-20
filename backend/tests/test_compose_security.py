from pathlib import Path
import tomllib

import yaml


def test_compose_project_and_database_volume_use_product_name():
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert compose["name"] == "blueskyarchive"
    assert compose["volumes"]["postgres-data"]["name"] == "blueskyarchive-postgres-data"


def test_backend_does_not_receive_fetcher_secrets_or_media_mount():
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    backend = compose["services"]["backend"]
    assert "env_file" not in backend
    assert "volumes" not in backend
    assert set(backend["environment"]) == {"DATABASE_URL", "APP_TIMEZONE"}


def test_fetcher_receives_only_its_own_declared_secrets():
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    fetcher = compose["services"]["fetcher"]
    assert "env_file" not in fetcher
    assert "BACKEND_DB_PASSWORD" not in str(fetcher["environment"])
    assert "BLSKY_IDENTIFIER" in fetcher["environment"]
    assert "BLSKY_APP_PASSWORD" in fetcher["environment"]


def test_fetcher_has_configurable_media_storage_limits():
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    fetcher_environment = compose["services"]["fetcher"]["environment"]
    assert fetcher_environment["SAVE_OWN_MEDIA"] == "${SAVE_OWN_MEDIA:-false}"
    assert {
        "SAVE_OWN_MEDIA",
        "MEDIA_MIN_FREE_BYTES",
        "MEDIA_MAX_FILE_BYTES",
        "MEDIA_MAX_TOTAL_BYTES",
        "MEDIA_TOTAL_SCAN_INTERVAL_SECONDS",
    }.issubset(fetcher_environment)


def test_database_migration_and_grants_complete_before_application_services():
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose["services"]
    assert services["db-migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["db-grants"]["depends_on"]["db-migrate"]["condition"] == "service_completed_successfully"
    assert services["backend"]["depends_on"]["db-grants"]["condition"] == "service_completed_successfully"
    assert services["fetcher"]["depends_on"]["db-grants"]["condition"] == "service_completed_successfully"
    assert "backend" not in services["fetcher"]["depends_on"]


def test_backend_and_fetcher_use_distinct_database_roles():
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    backend_url = compose["services"]["backend"]["environment"]["DATABASE_URL"]
    fetcher_url = compose["services"]["fetcher"]["environment"]["DATABASE_URL"]
    assert "BACKEND_DB_USER" in backend_url
    assert "FETCHER_DB_USER" in fetcher_url
    assert backend_url != fetcher_url


def test_backend_image_no_longer_runs_migrations_on_startup():
    dockerfile = (Path(__file__).parents[2] / "backend" / "Dockerfile").read_text(encoding="utf-8")
    command = dockerfile.split("CMD", 1)[1]
    assert "alembic" not in command
    assert "uvicorn" in command


def test_production_images_do_not_install_pytest():
    root = Path(__file__).parents[2]
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    groups = project["dependency-groups"]

    for service in ("backend", "fetcher"):
        assert all("pytest" not in dependency.lower() for dependency in groups[service])
        assert f"{service}/tests" in dockerignore

        dockerfile = (root / service / "Dockerfile").read_text(encoding="utf-8")
        assert dockerfile.startswith("FROM ghcr.io/astral-sh/uv:0.12.2 AS uv")
        assert "COPY pyproject.toml uv.lock ./" in dockerfile
        assert "uv sync --locked" in dockerfile
        assert f"--only-group {service}" in dockerfile
        assert "--no-default-groups" in dockerfile
        assert "requirements.txt" not in dockerfile
        runtime_stage = dockerfile.rsplit("FROM python:3.12-slim-bookworm", 1)[1]
        assert "COPY --from=builder /app/.venv /app/.venv" in runtime_stage
        assert "/usr/local/bin/uv" not in runtime_stage

    assert any(
        isinstance(dependency, str) and dependency.startswith("pytest==")
        for dependency in groups["dev"]
    )


def test_backend_and_fetcher_run_as_fixed_non_root_user():
    root = Path(__file__).parents[2]
    for service in ("backend", "fetcher"):
        dockerfile = (root / service / "Dockerfile").read_text(encoding="utf-8")
        assert "groupadd --gid 3006 blueskyarchive" in dockerfile
        assert "useradd --uid 3006 --gid 3006" in dockerfile
        assert "USER blueskyarchive:blueskyarchive" in dockerfile


def test_fetcher_does_not_restore_dac_override_capability():
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    fetcher = compose["services"]["fetcher"]
    assert fetcher["cap_drop"] == ["ALL"]
    assert "cap_add" not in fetcher


def test_all_services_have_bounded_json_file_logs():
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    expected = {
        "driver": "json-file",
        "options": {"max-size": "10m", "max-file": "3"},
    }
    for service in compose["services"].values():
        assert service["logging"] == expected


def test_nginx_is_published_on_ipv4_but_not_ipv6():
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert compose["services"]["nginx"]["ports"] == [
        "0.0.0.0:${HTTP_PORT:-8080}:8080"
    ]


def test_public_distribution_has_no_viewer_service_or_routes():
    root = Path(__file__).parents[2]
    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    nginx = (root / "nginx" / "default.conf").read_text(encoding="utf-8")
    frontend = (root / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")

    assert "viewer" not in compose["services"]
    assert "/viewer" not in nginx
    assert "/image-search" not in nginx
    assert "/viewer" not in frontend
    assert "公開ブロック一覧" not in frontend


def test_grant_script_enforces_least_privilege_and_self_checks():
    script = (Path(__file__).parents[2] / "postgres" / "grant_roles.sql").read_text(encoding="utf-8")
    assert "GRANT SELECT ON ALL TABLES" in script
    assert "GRANT INSERT (source, metadata_json) ON TABLE public.sync_states" in script
    assert "GRANT UPDATE (metadata_json, updated_at) ON TABLE public.sync_states" in script
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES" in script
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in script
    assert "NOT has_table_privilege(:'backend_user', 'public.posts', 'INSERT')" in script
    assert "source = %L" in script
    assert "backend_manual_sync_update" in script
    assert "NOT has_column_privilege(:'backend_user', 'public.sync_states', 'cursor', 'UPDATE')" in script
    assert "has_table_privilege(:'fetcher_user', 'public.posts', 'DELETE')" in script
