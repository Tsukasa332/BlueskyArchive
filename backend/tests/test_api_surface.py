import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")

from app.main import app


def test_api_documentation_routes_are_disabled():
    paths = {route.path for route in app.routes}
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/openapi.json" not in paths


def test_health_route_remains_available():
    assert "/api/health" in {route.path for route in app.routes}


def test_sidebar_navigation_routes_are_available():
    paths = {route.path for route in app.routes}
    assert "/api/navigation" in paths
    assert "/api/timeline/replies" in paths


def test_analytics_route_is_available():
    assert "/api/analytics" in {route.path for route in app.routes}
