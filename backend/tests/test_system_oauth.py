"""Tests for system-wide OAuth configuration and user mailbox isolation.

Verifies that users no longer configure per-user client IDs/secrets, that
deployment-wide credentials from the environment are used, that tokens and
caches remain strictly user-isolated and encrypted, and that secrets never leak.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.core.crypto import decrypt_secret
from app.models.enums import ConnectionStatus
from app.models.mail_account import MailAccount
from app.repositories.oauth_clients import OAuthClientRepository
from tests.fakes import FakeProviderState

SENSITIVE_STRINGS = [
    "test-google-client-secret",
    "test-microsoft-client-secret",
    "access-token-1",
    "refresh-token-1",
    "msal-cache-1",
]


def assert_no_secrets_in_payload(obj: object) -> None:
    """Recursively checks that no secrets or raw tokens leak in the response payload."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in {
                "client_secret",
                "client_secret_encrypted",
                "access_token",
                "access_token_encrypted",
                "refresh_token",
                "refresh_token_encrypted",
                "cache_serialized",
                "token_cache",
                "token_cache_encrypted",
            }, f"Forbidden key '{k}' found in payload!"
            assert_no_secrets_in_payload(v)
    elif isinstance(obj, list):
        for item in obj:
            assert_no_secrets_in_payload(item)
    elif isinstance(obj, str):
        for secret in SENSITIVE_STRINGS:
            assert secret not in obj, f"Secret '{secret}' leaked in string: '{obj}'"


@pytest.fixture
def fake_oauth(monkeypatch, fake_providers):
    """Installs fake providers and mocks ClientFactory in oauth_service and mail_scan_service."""

    def _install(**kwargs):
        factory, clients = fake_providers(**kwargs)
        monkeypatch.setattr(
            "app.services.oauth_service.ClientFactory", lambda *a, **k: factory
        )
        return factory, clients

    return _install


def test_gmail_connect_uses_system_credentials(api_user1, fake_oauth):
    _, clients = fake_oauth(gmail=FakeProviderState())
    response = api_user1.post("/api/v1/integrations/gmail/connect")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "gmail"
    assert "https://provider.test/authorize?state=" in body["authorization_url"]
    assert body["redirect_uri"].endswith("/api/v1/integrations/gmail/callback")
    assert_no_secrets_in_payload(body)


def test_outlook_connect_uses_system_credentials(api_user1, fake_oauth):
    _, clients = fake_oauth(outlook=FakeProviderState())
    response = api_user1.post("/api/v1/integrations/outlook/connect")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "outlook"
    assert "https://provider.test/authorize?state=" in body["authorization_url"]
    assert body["redirect_uri"].endswith("/api/v1/integrations/outlook/callback")
    assert_no_secrets_in_payload(body)


def test_user_does_not_need_oauth_client_config(api_user1, db, user1, fake_oauth):
    repo = OAuthClientRepository(db)
    assert repo.get_for_user_provider(user1.id, "gmail") is None
    assert repo.get_for_user_provider(user1.id, "outlook") is None

    fake_oauth(gmail=FakeProviderState())
    response = api_user1.post("/api/v1/integrations/gmail/connect")
    assert response.status_code == 200


def test_google_not_configured_returns_controlled_error(api_user1, monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", None)
    response = api_user1.post("/api/v1/integrations/gmail/connect")
    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["code"] == "oauth_not_configured"
    assert "yapılandırılmamış" in body["detail"]["message"]


def test_microsoft_not_configured_returns_controlled_error(api_user1, monkeypatch):
    monkeypatch.setattr(settings, "microsoft_oauth_client_id", None)
    response = api_user1.post("/api/v1/integrations/outlook/connect")
    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["code"] == "oauth_not_configured"
    assert "yapılandırılmamış" in body["detail"]["message"]


def test_gmail_callback_stores_user_specific_tokens(api_user1, db, user1, fake_oauth):
    _, clients = fake_oauth(
        gmail=FakeProviderState(
            identity=__import__("app.integrations.base", fromlist=["ProviderIdentity"]).ProviderIdentity(
                email_address="alice@gmail.com",
                provider_account_id="google-alice-id",
                display_name="Alice Gmail",
            ),
            access_token="alice-access-token",
            refresh_token="alice-refresh-token",
        )
    )
    api_user1.post("/api/v1/integrations/gmail/connect")
    state = clients["gmail"].last_state

    response = api_user1.get(
        f"/api/v1/integrations/gmail/callback?code=code-1&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "oauth=success" in response.headers["location"]
    assert "alice%40gmail.com" in response.headers["location"]

    account = (
        db.query(MailAccount)
        .filter(MailAccount.user_id == user1.id, MailAccount.provider == "gmail")
        .one()
    )
    assert account.email_address == "alice@gmail.com"
    assert account.provider_account_id == "google-alice-id"
    assert account.status == ConnectionStatus.CONNECTED.value
    assert decrypt_secret(account.access_token_encrypted) == "alice-access-token"
    assert decrypt_secret(account.refresh_token_encrypted) == "alice-refresh-token"

    # Verify listing endpoint never returns encrypted or raw tokens
    accounts_resp = api_user1.get("/api/v1/integrations/accounts")
    assert accounts_resp.status_code == 200
    assert_no_secrets_in_payload(accounts_resp.json())


def test_outlook_callback_stores_user_specific_cache(api_user1, db, user1, fake_oauth):
    _, clients = fake_oauth(
        outlook=FakeProviderState(
            identity=__import__("app.integrations.base", fromlist=["ProviderIdentity"]).ProviderIdentity(
                email_address="alice@hotmail.com",
                provider_account_id="ms-alice-id",
                display_name="Alice Hotmail",
            ),
            access_token="alice-ms-token",
            cache_serialized="alice-msal-cache-blob",
        )
    )
    api_user1.post("/api/v1/integrations/outlook/connect")
    state = clients["outlook"].last_state

    response = api_user1.get(
        f"/api/v1/integrations/outlook/callback?code=code-ms&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "oauth=success" in response.headers["location"]
    assert "alice%40hotmail.com" in response.headers["location"]

    account = (
        db.query(MailAccount)
        .filter(MailAccount.user_id == user1.id, MailAccount.provider == "outlook")
        .one()
    )
    assert account.email_address == "alice@hotmail.com"
    assert account.status == ConnectionStatus.CONNECTED.value
    assert decrypt_secret(account.token_cache_encrypted) == "alice-msal-cache-blob"

    accounts_resp = api_user1.get("/api/v1/integrations/accounts")
    assert accounts_resp.status_code == 200
    assert_no_secrets_in_payload(accounts_resp.json())


def test_two_users_share_client_id_but_not_tokens(
    api_user1, api_user2, db, user1, user2, fake_oauth
):
    from app.integrations.base import ProviderIdentity

    # User 1 connects
    _, clients1 = fake_oauth(
        gmail=FakeProviderState(
            identity=ProviderIdentity(
                email_address="user1@gmail.com",
                provider_account_id="sub-1",
            ),
            access_token="token-user1",
        )
    )
    api_user1.post("/api/v1/integrations/gmail/connect")
    state1 = clients1["gmail"].last_state
    api_user1.get(
        f"/api/v1/integrations/gmail/callback?code=code-1&state={state1}",
        follow_redirects=False,
    )

    # User 2 connects
    _, clients2 = fake_oauth(
        gmail=FakeProviderState(
            identity=ProviderIdentity(
                email_address="user2@gmail.com",
                provider_account_id="sub-2",
            ),
            access_token="token-user2",
        )
    )
    api_user2.post("/api/v1/integrations/gmail/connect")
    state2 = clients2["gmail"].last_state
    api_user2.get(
        f"/api/v1/integrations/gmail/callback?code=code-2&state={state2}",
        follow_redirects=False,
    )

    # Check database isolation
    acc1 = db.query(MailAccount).filter(MailAccount.user_id == user1.id).one()
    acc2 = db.query(MailAccount).filter(MailAccount.user_id == user2.id).one()
    assert acc1.id != acc2.id
    assert acc1.email_address == "user1@gmail.com"
    assert acc2.email_address == "user2@gmail.com"
    assert decrypt_secret(acc1.access_token_encrypted) == "token-user1"
    assert decrypt_secret(acc2.access_token_encrypted) == "token-user2"

    # User 1 cannot see User 2's accounts
    u1_accounts = api_user1.get("/api/v1/integrations/accounts").json()
    assert len(u1_accounts) == 1
    assert u1_accounts[0]["email_address"] == "user1@gmail.com"

    # User 2 cannot see User 1's accounts
    u2_accounts = api_user2.get("/api/v1/integrations/accounts").json()
    assert len(u2_accounts) == 1
    assert u2_accounts[0]["email_address"] == "user2@gmail.com"


def test_cross_user_account_access_denied(
    api_user1, api_user2, db, user1, fake_oauth
):
    from app.integrations.base import ProviderIdentity

    _, clients = fake_oauth(
        gmail=FakeProviderState(
            identity=ProviderIdentity(
                email_address="user1@gmail.com",
                provider_account_id="sub-1",
            ),
        )
    )
    api_user1.post("/api/v1/integrations/gmail/connect")
    state = clients["gmail"].last_state
    api_user1.get(
        f"/api/v1/integrations/gmail/callback?code=code-1&state={state}",
        follow_redirects=False,
    )

    acc1 = db.query(MailAccount).filter(MailAccount.user_id == user1.id).one()

    # User 2 tries to test user 1's account -> 404
    resp = api_user2.post(f"/api/v1/integrations/accounts/{acc1.id}/test")
    assert resp.status_code == 404

    # User 2 tries to reconnect user 1's account -> 404
    resp = api_user2.post(f"/api/v1/integrations/accounts/{acc1.id}/reconnect")
    assert resp.status_code == 404

    # User 2 tries to update user 1's account -> 404
    resp = api_user2.patch(f"/api/v1/integrations/accounts/{acc1.id}", json={"display_name": "Hack"})
    assert resp.status_code == 404

    # User 2 tries to disconnect user 1's account -> 404
    resp = api_user2.delete(f"/api/v1/integrations/accounts/{acc1.id}")
    assert resp.status_code == 404


def test_disconnect_removes_only_current_users_tokens(
    api_user1, api_user2, db, user1, user2, fake_oauth
):
    from app.integrations.base import ProviderIdentity

    _, clients1 = fake_oauth(
        gmail=FakeProviderState(
            identity=ProviderIdentity(email_address="u1@gmail.com", provider_account_id="sub-1"),
            access_token="tok1",
        )
    )
    api_user1.post("/api/v1/integrations/gmail/connect")
    api_user1.get(
        f"/api/v1/integrations/gmail/callback?code=c&state={clients1['gmail'].last_state}",
        follow_redirects=False,
    )

    _, clients2 = fake_oauth(
        gmail=FakeProviderState(
            identity=ProviderIdentity(email_address="u2@gmail.com", provider_account_id="sub-2"),
            access_token="tok2",
        )
    )
    api_user2.post("/api/v1/integrations/gmail/connect")
    api_user2.get(
        f"/api/v1/integrations/gmail/callback?code=c&state={clients2['gmail'].last_state}",
        follow_redirects=False,
    )

    acc1 = db.query(MailAccount).filter(MailAccount.user_id == user1.id).one()
    acc2 = db.query(MailAccount).filter(MailAccount.user_id == user2.id).one()

    # User 1 disconnects their account
    resp = api_user1.delete(f"/api/v1/integrations/accounts/{acc1.id}")
    assert resp.status_code == 200

    db.refresh(acc1)
    db.refresh(acc2)

    assert acc1.status == ConnectionStatus.DISCONNECTED.value
    assert acc1.access_token_encrypted is None

    # User 2's account is completely untouched
    assert acc2.status == ConnectionStatus.CONNECTED.value
    assert acc2.access_token_encrypted is not None
    assert decrypt_secret(acc2.access_token_encrypted) == "tok2"


def test_reconnect_uses_system_client(api_user1, db, user1, fake_oauth):
    from app.integrations.base import ProviderIdentity

    _, clients = fake_oauth(
        gmail=FakeProviderState(
            identity=ProviderIdentity(email_address="alice@gmail.com", provider_account_id="sub-1"),
        )
    )
    api_user1.post("/api/v1/integrations/gmail/connect")
    api_user1.get(
        f"/api/v1/integrations/gmail/callback?code=c&state={clients['gmail'].last_state}",
        follow_redirects=False,
    )

    acc = db.query(MailAccount).filter(MailAccount.user_id == user1.id).one()
    reconnect_resp = api_user1.post(f"/api/v1/integrations/accounts/{acc.id}/reconnect")
    assert reconnect_resp.status_code == 200
    body = reconnect_resp.json()
    assert body["provider"] == "gmail"
    assert "https://provider.test/authorize?state=" in body["authorization_url"]
    assert_no_secrets_in_payload(body)


def test_recursive_assertion_no_secrets_in_any_integration_endpoints(
    api_user1, fake_oauth
):
    fake_oauth(gmail=FakeProviderState(), outlook=FakeProviderState())

    # 1. Overview
    resp = api_user1.get("/api/v1/integrations")
    assert resp.status_code == 200
    assert_no_secrets_in_payload(resp.json())

    # 2. Accounts list
    resp = api_user1.get("/api/v1/integrations/accounts")
    assert resp.status_code == 200
    assert_no_secrets_in_payload(resp.json())

    # 3. Connect endpoints
    resp = api_user1.post("/api/v1/integrations/gmail/connect")
    assert resp.status_code == 200
    assert_no_secrets_in_payload(resp.json())

    resp = api_user1.post("/api/v1/integrations/outlook/connect")
    assert resp.status_code == 200
    assert_no_secrets_in_payload(resp.json())
