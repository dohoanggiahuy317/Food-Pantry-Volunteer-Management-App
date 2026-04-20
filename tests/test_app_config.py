from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def production_app(monkeypatch):
    monkeypatch.setenv("AUTH_PROVIDER", "memory")
    monkeypatch.setenv("DATA_BACKEND", "memory")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    sys.modules.pop("app", None)
    module = importlib.import_module("app")
    yield module
    sys.modules.pop("app", None)


def test_healthcheck_returns_ok(production_app):
    production_app.app.config.update(TESTING=True)
    client = production_app.app.test_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_production_defaults_enable_secure_sessions(production_app):
    assert production_app.app.config["SESSION_COOKIE_SECURE"] is True
    assert production_app.app.config["PREFERRED_URL_SCHEME"] == "https"
