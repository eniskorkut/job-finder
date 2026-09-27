"""Phase 3 endpoints stay honestly unimplemented; phase 2 endpoints now work."""

from __future__ import annotations

import pytest


def test_telegram_link_is_not_implemented(api_user1):
    response = api_user1.post("/api/v1/integrations/telegram/link")
    assert response.status_code == 501
    assert response.json()["detail"]["phase"] == "phase-3"


def test_notification_test_is_not_implemented(api_user1):
    response = api_user1.post("/api/v1/notifications/test")
    assert response.status_code == 501


def test_connect_requires_saved_client_credentials(api_user1):
    """No credentials stored yet: the API explains what to do instead of 501."""
    for provider in ("gmail", "outlook"):
        response = api_user1.post(f"/api/v1/integrations/{provider}/connect")
        assert response.status_code == 422
        assert "istemci bilgileri" in response.json()["detail"]["message"]


def test_integrations_report_phase2_availability(api_user1, monkeypatch):
    response = api_user1.get("/api/v1/integrations")
    assert response.status_code == 200
    body = response.json()
    providers = {item["provider"]: item for item in body["integrations"]}

    for provider in ("gmail", "outlook"):
        item = providers[provider]
        assert item["available"] is True
        assert item["phase"] == "phase-2"
        assert item["oauth_client"]["configured"] is False
        assert item["oauth_client"]["redirect_uri"].endswith(f"/{provider}/callback")
        assert item["capabilities"]["first_scan_window_days"] >= 1

    telegram = providers["telegram"]
    assert telegram["available"] is False
    assert telegram["phase"] == "phase-3"

    # The shared DeepSeek key is reported by presence only, never by value.
    assert body["deepseek"]["shared"] is True
    assert body["deepseek"]["configured"] is False
    assert "api_key" not in body["deepseek"]


def test_deepseek_summary_never_exposes_the_key(api_user1, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "deepseek_api_key", "super-secret-key-value")
    response = api_user1.get("/api/v1/integrations")
    body = response.json()
    assert body["deepseek"]["configured"] is True
    serialized = response.text
    assert "super-secret-key-value" not in serialized


def test_sync_status_reports_worker_hint(api_user1):
    response = api_user1.get("/api/v1/sync/status")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["running"] is False
    assert body["worker_hint"] == "python -m app.worker"


def test_sync_run_requires_a_connected_account(api_user1, db):
    response = api_user1.post("/api/v1/sync/run")
    assert response.status_code == 422
    assert "Bağlı bir e-posta hesabı yok" in response.json()["detail"]["message"]


@pytest.mark.parametrize("provider", ["gmail", "outlook"])
def test_callback_without_state_redirects_with_reason(api_user1, provider):
    response = api_user1.get(
        f"/api/v1/integrations/{provider}/callback",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "oauth=error" in response.headers["location"]
    assert "reason=state_missing" in response.headers["location"]


def test_disconnect_requires_ownership(api_user1, api_user2):
    integrations = api_user1.get("/api/v1/integrations").json()
    gmail = next(item for item in integrations["integrations"] if item["provider"] == "gmail")
    if gmail["accounts"]:
        account_id = gmail["accounts"][0]["id"]
        # A different user cannot touch another user's mailbox row.
        assert (
            api_user2.delete(f"/api/v1/integrations/accounts/{account_id}").status_code
            == 404
        )
