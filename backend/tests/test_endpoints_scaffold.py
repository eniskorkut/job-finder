"""Phase 2/3 endpoints must answer 501 - never a fake success."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("provider", ["gmail", "outlook"])
def test_mail_connect_is_not_implemented(api_user1, provider):
    response = api_user1.post(f"/api/v1/integrations/{provider}/connect")
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert detail["code"] == "not_implemented"
    assert detail["phase"] == "phase-2"


def test_telegram_link_is_not_implemented(api_user1):
    response = api_user1.post("/api/v1/integrations/telegram/link")
    assert response.status_code == 501
    assert response.json()["detail"]["phase"] == "phase-3"


def test_sync_run_is_not_implemented(api_user1):
    response = api_user1.post("/api/v1/sync/run")
    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "not_implemented"


def test_notification_test_is_not_implemented(api_user1):
    response = api_user1.post("/api/v1/notifications/test")
    assert response.status_code == 501


def test_integrations_report_unavailable_and_configured_state(api_user1, monkeypatch):
    response = api_user1.get("/api/v1/integrations")
    assert response.status_code == 200
    body = response.json()
    providers = {item["provider"]: item for item in body["integrations"]}
    assert set(providers) == {"gmail", "outlook", "telegram"}
    for item in providers.values():
        assert item["available"] is False
        assert item["unavailable_reason"]
        assert item["phase"] in {"phase-2", "phase-3"}
    assert body["deepseek"]["enabled"] is False
    assert body["deepseek"]["shared"] is True
    assert body["deepseek"]["configured"] is False


def test_sync_status_is_honest(api_user1):
    response = api_user1.get("/api/v1/sync/status")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["running"] is False
    assert "aşamada" in body["message"]


def test_disconnect_requires_ownership(api_user1, api_user2):
    integrations = api_user1.get("/api/v1/integrations").json()
    gmail = next(item for item in integrations["integrations"] if item["provider"] == "gmail")
    if gmail["accounts"]:
        account_id = gmail["accounts"][0]["id"]
        # A different user cannot delete another user's account row.
        assert (
            api_user2.delete(f"/api/v1/integrations/gmail/accounts/{account_id}").status_code
            == 404
        )
