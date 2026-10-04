"""Phase 3 endpoints stay honestly unimplemented; phase 2 endpoints now work."""

from __future__ import annotations

import pytest


def test_telegram_token_must_be_valid(api_user1):
    """Phase 3 implements Telegram; an unverified token is refused, never faked."""
    response = api_user1.post(
        "/api/v1/integrations/telegram/config",
        json={"bot_token": "gecersiz-token-format"},
    )
    assert response.status_code == 422
    assert "token" in response.json()["detail"]["message"].lower()


def test_notification_test_requires_a_configured_bot(api_user1):
    """No token/chat saved yet: the API explains the missing setup instead of 501."""
    response = api_user1.post("/api/v1/notifications/test")
    assert response.status_code == 422
    assert "Telegram" in response.json()["detail"]["message"]


def test_connect_requires_system_oauth_configuration(api_user1, monkeypatch):
    """When deployment OAuth is not configured, connect explains the missing setup."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "google_oauth_client_id", None)
    monkeypatch.setattr(settings, "microsoft_oauth_client_id", None)
    for provider in ("gmail", "outlook"):
        response = api_user1.post(f"/api/v1/integrations/{provider}/connect")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "oauth_not_configured"


def test_integrations_report_phase2_availability(api_user1, monkeypatch):
    response = api_user1.get("/api/v1/integrations")
    assert response.status_code == 200
    body = response.json()
    providers = {item["provider"]: item for item in body["integrations"]}

    for provider in ("gmail", "outlook"):
        item = providers[provider]
        assert item["available"] is True
        assert item["phase"] == "phase-2"
        assert item["configured"] is True
        assert item["oauth_client"] is None
        assert item["mode"] == "personal_accounts"
        assert item["capabilities"]["first_scan_window_days"] >= 1

    # Phase 3 replaced the phase-2 telegram stub with a real per-user
    # integration, so it is now available and reports its own config state.
    telegram = providers["telegram"]
    assert telegram["available"] is True
    assert telegram["phase"] == "phase-3"
    assert telegram["status"] == "disconnected"
    assert telegram["capabilities"]["implemented"] is True
    assert telegram["capabilities"]["chat_id"] is None

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
    assert body["deepseek"]["shared"] is True
    # Only presence/model summary is exposed - never the key itself.
    assert "api_key" not in body["deepseek"]
    assert "super-secret-key-value" not in response.text


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
