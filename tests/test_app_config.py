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


def test_public_homepage_links_to_privacy_policy(production_app):
    production_app.app.config.update(TESTING=True)
    client = production_app.app.test_client()

    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Volunteer Management System" in body
    assert 'href="/privacy"' in body
    assert 'href="/dashboard"' in body
    assert "Google Calendar sync is optional" in body


def test_public_privacy_policy_loads_without_login(production_app):
    production_app.app.config.update(TESTING=True)
    client = production_app.app.test_client()

    response = client.get("/privacy")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Privacy Policy" in body
    assert "Google Calendar Data" in body
    assert 'href="/privacy"' in body


def test_dashboard_route_still_serves_app(production_app):
    production_app.app.config.update(TESTING=True)
    client = production_app.app.test_client()

    response = client.get("/dashboard")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "auth-shell" in body
    assert "dashboard.js" in body


def test_production_defaults_enable_secure_sessions(production_app):
    assert production_app.app.config["SESSION_COOKIE_SECURE"] is True
    assert production_app.app.config["PREFERRED_URL_SCHEME"] == "https"
