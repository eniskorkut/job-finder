"""OAuth client credentials and the authorization-code flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.crypto import decrypt_secret
from app.models.enums import ConnectionStatus
from app.models.mail_account import MailAccount
from app.models.oauth import OAuthState
from app.models.sync_job import ProcessedMessage, SyncCheckpoint  # noqa: F401
from tests.fakes import FakeProviderState

GMAIL_CLIENT = {
    "client_id": "1234567890-abc.apps.googleusercontent.com",
    "client_secret": "google-client-secret-value",
}


def save_gmail_client(api, **overrides) -> dict:
    payload = {**GMAIL_CLIENT, **overrides}
    response = api.put("/api/v1/integrations/gmail/client", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def fake_oauth(monkeypatch, fake_providers):
    """Install a fake provider client for the OAuth service (no HTTP)."""

    def _install(provider: str = "gmail", **state_kwargs):
        state = FakeProviderState(**state_kwargs)
        factory, clients = fake_providers(**{provider: state})
        monkeypatch.setattr(
            "app.services.oauth_service.ClientFactory", lambda *args, **kwargs: factory
        )
        return factory, clients[provider]

    return _install


class TestClientCredentials:
    def test_saving_credentials_masks_the_secret_and_encrypts_at_rest(
        self, api_user1, db, user1
    ):
        body = save_gmail_client(api_user1)
        assert body["configured"] is True
        assert body["client_id"] == GMAIL_CLIENT["client_id"]
        assert body["client_secret_hint"].endswith("alue")
        assert "google-client-secret-value" not in str(body)

        from app.repositories.oauth_clients import OAuthClientRepository

        config = OAuthClientRepository(db).get_for_user_provider(user1.id, "gmail")
        assert config.client_secret_encrypted != GMAIL_CLIENT["client_secret"]
        assert decrypt_secret(config.client_secret_encrypted) == GMAIL_CLIENT["client_secret"]
        assert config.redirect_uri.endswith("/api/v1/integrations/gmail/callback")

    def test_update_without_secret_keeps_the_stored_one(self, api_user1, db, user1):
        save_gmail_client(api_user1)
        body = save_gmail_client(api_user1, client_id="new-client-id.apps.googleusercontent.com", client_secret=None)
        assert body["client_id"] == "new-client-id.apps.googleusercontent.com"
        assert body["client_secret_hint"].endswith("alue")

        from app.repositories.oauth_clients import OAuthClientRepository

        config = OAuthClientRepository(db).get_for_user_provider(user1.id, "gmail")
        assert decrypt_secret(config.client_secret_encrypted) == GMAIL_CLIENT["client_secret"]

    def test_first_save_requires_a_secret(self, api_user1):
        response = api_user1.put(
            "/api/v1/integrations/gmail/client",
            json={"client_id": "1234567890-abc.apps.googleusercontent.com"},
        )
        assert response.status_code == 422
        assert "Client Secret" in response.json()["detail"]["message"]

    def test_credentials_are_per_user(self, api_user1, api_user2, db, user1, user2):
        save_gmail_client(api_user1)
        listing = api_user2.get("/api/v1/integrations").json()
        gmail = next(i for i in listing["integrations"] if i["provider"] == "gmail")
        assert gmail["oauth_client"]["configured"] is False

        from app.repositories.oauth_clients import OAuthClientRepository

        repo = OAuthClientRepository(db)
        assert repo.get_for_user_provider(user1.id, "gmail") is not None
        assert repo.get_for_user_provider(user2.id, "gmail") is None

    def test_delete_client_marks_accounts_for_reauth(self, api_user1, db, user1, mailbox, fake_oauth):
        fake_oauth("gmail")
        account = mailbox("gmail")
        response = api_user1.delete("/api/v1/integrations/gmail/client")
        assert response.status_code == 200
        db.refresh(account)
        assert account.status == ConnectionStatus.NEEDS_REAUTH.value
        assert "yeniden" in (account.last_error or "").lower()

    def test_integrations_overview_includes_server_managed_web_search_and_rich_guides(
        self, api_user1
    ):
        response = api_user1.get("/api/v1/integrations")
        assert response.status_code == 200
        body = response.json()
        assert "deepseek" in body
        assert "web_search" in body
        assert body["web_search"]["provider"] in {"searxng", "mock", "none"}
        assert body["web_search"]["mode"] == "server_managed"
        assert "kullanıcı API anahtarı gerekmez" in body["web_search"]["description"]

        gmail = next(i for i in body["integrations"] if i["provider"] == "gmail")
        client = gmail["oauth_client"]
        assert client["estimated_minutes"] == 5
        assert len(client["structured_steps"]) >= 5
        assert len(client["faq"]) >= 2
        assert any("API Key" in f["question"] for f in client["faq"])
        assert any(t["error_code"] == "redirect_uri_mismatch" for t in client["troubleshooting"])
        assert any(l["label"] == "Google Cloud Console" for l in client["official_links"])

    def test_saving_credentials_returns_rich_wizard_structure(self, api_user1):
        body = save_gmail_client(api_user1)
        assert body["configured"] is True
        assert body["estimated_minutes"] == 5
        assert len(body["structured_steps"]) >= 5
        assert any("Google Cloud" in s["title"] for s in body["structured_steps"])
        assert any(t["error_code"] == "redirect_uri_mismatch" for t in body["troubleshooting"])

    def test_unsupported_provider_is_rejected(self, api_user1):
        response = api_user1.put(
            "/api/v1/integrations/telegram/client",
            json={"client_id": "x" * 20, "client_secret": "y" * 20},
        )
        assert response.status_code == 422


class TestConnect:
    def test_connect_builds_authorization_url_with_pkce_state(self, api_user1, db, user1, fake_oauth):
        save_gmail_client(api_user1)
        _, client = fake_oauth("gmail")

        response = api_user1.post("/api/v1/integrations/gmail/connect")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["authorization_url"].startswith("https://provider.test/authorize?state=")
        assert body["redirect_uri"].endswith("/api/v1/integrations/gmail/callback")

        state = client.last_state
        assert state and getattr(client, "last_code_challenge")

        from app.repositories.oauth import OAuthStateRepository

        stored = OAuthStateRepository(db).get_by_state(state)
        assert stored is not None
        assert stored.user_id == user1.id
        assert stored.session_id is not None
        assert stored.consumed_at is None

    def test_starting_a_new_flow_invalidates_the_previous_state(
        self, api_user1, db, user1, fake_oauth
    ):
        save_gmail_client(api_user1)
        _, client = fake_oauth("gmail")
        api_user1.post("/api/v1/integrations/gmail/connect")
        first_state = client.last_state
        api_user1.post("/api/v1/integrations/gmail/connect")

        from app.repositories.oauth import OAuthStateRepository

        assert OAuthStateRepository(db).get_valid(first_state) is None

    def test_connect_requires_authentication(self, api, user1):
        assert api.post("/api/v1/integrations/gmail/connect").status_code == 401


class TestCallback:
    def test_successful_callback_links_the_verified_mailbox(
        self, api_user1, db, user1, fake_oauth
    ):
        save_gmail_client(api_user1)
        _, client = fake_oauth(
            "gmail",
            identity=__import__("app.integrations.base", fromlist=["ProviderIdentity"]).ProviderIdentity(
                email_address="gercek.hesap@gmail.com",
                provider_account_id="google-sub-1",
                display_name="Gerçek Hesap",
            ),
        )
        start = api_user1.post("/api/v1/integrations/gmail/connect").json()
        state = client.last_state

        response = api_user1.get(
            f"/api/v1/integrations/gmail/callback?code=auth-code-1&state={state}",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "oauth=success" in response.headers["location"]
        assert "gercek.hesap%40gmail.com" in response.headers["location"]

        account = db.query(MailAccount).filter(MailAccount.user_id == user1.id).one()
        # The address comes from the provider, never from the client.
        assert account.email_address == "gercek.hesap@gmail.com"
        assert account.provider_account_id == "google-sub-1"
        assert account.status == ConnectionStatus.CONNECTED.value
        assert account.access_token_encrypted and "access-token-1" not in account.access_token_encrypted
        assert account.refresh_token_encrypted
        assert account.token_expires_at is not None
        assert account.scopes == client.capabilities.scopes

        from app.repositories.sync_jobs import CheckpointRepository

        assert CheckpointRepository(db).get_for_account(account.id) is not None

    def test_state_is_single_use(self, api_user1, db, fake_oauth):
        save_gmail_client(api_user1)
        _, client = fake_oauth("gmail", refresh_token=None)
        api_user1.post("/api/v1/integrations/gmail/connect")
        state = client.last_state
        url = f"/api/v1/integrations/gmail/callback?code=c&state={state}"

        first = api_user1.get(url, follow_redirects=False)
        assert "oauth=success" in first.headers["location"]

        second = api_user1.get(url, follow_redirects=False)
        assert "oauth=error" in second.headers["location"]
        assert "forbidden" in second.headers["location"]

    def test_expired_state_is_rejected(self, api_user1, db, fake_oauth):
        save_gmail_client(api_user1)
        _, client = fake_oauth("gmail")
        api_user1.post("/api/v1/integrations/gmail/connect")
        state = client.last_state

        stored = db.query(OAuthState).filter(OAuthState.provider == "gmail").one()
        stored.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

        response = api_user1.get(
            f"/api/v1/integrations/gmail/callback?code=c&state={state}",
            follow_redirects=False,
        )
        assert "oauth=error" in response.headers["location"]

    def test_cross_user_state_is_rejected(
        self, api_user1, api_user2, db, user1, user2, fake_oauth
    ):
        save_gmail_client(api_user1)
        _, client = fake_oauth("gmail")
        api_user1.post("/api/v1/integrations/gmail/connect")
        state = client.last_state

        # User2's browser cannot complete user1's flow.
        response = api_user2.get(
            f"/api/v1/integrations/gmail/callback?code=c&state={state}",
            follow_redirects=False,
        )
        assert "oauth=error" in response.headers["location"]
        assert db.query(MailAccount).filter(MailAccount.user_id == user1.id).count() == 0

    def test_provider_error_is_reported(self, api_user1, fake_oauth):
        save_gmail_client(api_user1)
        _, client = fake_oauth("gmail")
        api_user1.post("/api/v1/integrations/gmail/connect")
        state = client.last_state
        response = api_user1.get(
            f"/api/v1/integrations/gmail/callback?error=access_denied&state={state}",
            follow_redirects=False,
        )
        assert "oauth=error" in response.headers["location"]
        # The provider's reason is surfaced instead of a generic failure.
        assert "access_denied" in response.headers["location"].replace("%3A", ":").replace("%20", " ")

    def test_second_mailbox_with_same_client(self, api_user1, db, user1, fake_oauth):
        from app.integrations.base import ProviderIdentity

        save_gmail_client(api_user1)
        _, client = fake_oauth("gmail")
        api_user1.post("/api/v1/integrations/gmail/connect")
        api_user1.get(
            f"/api/v1/integrations/gmail/callback?code=c1&state={client.last_state}",
            follow_redirects=False,
        )

        client.state.identity = ProviderIdentity(
            email_address="ikinci.hesap@gmail.com", provider_account_id="google-sub-2"
        )
        api_user1.post("/api/v1/integrations/gmail/connect")
        api_user1.get(
            f"/api/v1/integrations/gmail/callback?code=c2&state={client.last_state}",
            follow_redirects=False,
        )

        accounts = (
            db.query(MailAccount).filter(MailAccount.user_id == user1.id).order_by(MailAccount.email_address).all()
        )
        # First link used the default fake identity, second one the new address.
        assert [a.email_address for a in accounts] == [
            "fake@example.com",
            "ikinci.hesap@gmail.com",
        ]


class TestAccountMaintenance:
    def test_listing_never_returns_secrets_or_tokens(self, api_user1, monkeypatch, fake_providers):
        from app.integrations.base import ProviderIdentity

        state = FakeProviderState(
            identity=ProviderIdentity(
                email_address="hesap@gmail.com", provider_account_id="sub-9"
            )
        )
        factory, _ = fake_providers(gmail=state)
        monkeypatch.setattr(
            "app.services.oauth_service.ClientFactory", lambda *a, **k: factory
        )
        save_gmail_client(api_user1)
        api_user1.post("/api/v1/integrations/gmail/connect")
        client = factory.clients["gmail"]
        api_user1.get(
            f"/api/v1/integrations/gmail/callback?code=c&state={client.last_state}",
            follow_redirects=False,
        )

        response = api_user1.get("/api/v1/integrations")
        text = response.text
        assert "google-client-secret-value" not in text
        assert "access-token-1" not in text
        assert "refresh-token-1" not in text

        gmail = next(i for i in response.json()["integrations"] if i["provider"] == "gmail")
        assert gmail["accounts"][0]["email_address"] == "hesap@gmail.com"
        assert gmail["accounts"][0]["status"] == "connected"

    def test_test_connection_refreshes_and_reports_ok(self, api_user1, db, monkeypatch, fake_providers):
        state = FakeProviderState()
        factory, _ = fake_providers(gmail=state)
        monkeypatch.setattr(
            "app.services.oauth_service.ClientFactory", lambda *a, **k: factory
        )
        save_gmail_client(api_user1)
        account = self._link(api_user1, factory, db)

        response = api_user1.post(f"/api/v1/integrations/accounts/{account.id}/test")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ok"] is True
        assert factory.clients["gmail"].state.refresh_requests
        assert factory.clients["gmail"].state.refresh_requests[-1]["refresh_token"] == "refresh-token-1"

    def test_test_connection_reports_reauth_needed(self, api_user1, db, monkeypatch, fake_providers):
        from app.integrations.errors import ProviderAuthError

        state = FakeProviderState(
            refresh_error=ProviderAuthError("yenileme başarısız", provider="gmail")
        )
        factory, _ = fake_providers(gmail=state)
        monkeypatch.setattr(
            "app.services.oauth_service.ClientFactory", lambda *a, **k: factory
        )
        save_gmail_client(api_user1)
        account = self._link(api_user1, factory, db)

        body = api_user1.post(f"/api/v1/integrations/accounts/{account.id}/test").json()
        assert body["ok"] is False
        assert body["status"] == ConnectionStatus.NEEDS_REAUTH.value

    def test_filters_can_be_updated_and_cursor_reset(self, api_user1, db, monkeypatch, fake_providers):
        factory, _ = fake_providers(gmail=FakeProviderState())
        monkeypatch.setattr(
            "app.services.oauth_service.ClientFactory", lambda *a, **k: factory
        )
        save_gmail_client(api_user1)
        account = self._link(api_user1, factory, db)

        response = api_user1.patch(
            f"/api/v1/integrations/accounts/{account.id}",
            json={
                "display_name": "Kariyer Kutusu",
                "senders": ["linkedin.com", "kariyer@firma.com"],
                "subjects": ["iş ilanı"],
                "reset_cursor": True,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["display_name"] == "Kariyer Kutusu"
        assert body["filters"]["senders"] == ["linkedin.com", "kariyer@firma.com"]

    def test_disconnect_clears_tokens_but_keeps_jobs(
        self, api_user1, db, user1, monkeypatch, fake_providers
    ):
        from app.models.job import Job

        factory, _ = fake_providers(gmail=FakeProviderState())
        monkeypatch.setattr(
            "app.services.oauth_service.ClientFactory", lambda *a, **k: factory
        )
        save_gmail_client(api_user1)
        account = self._link(api_user1, factory, db)
        db.add(
            Job(
                user_id=user1.id,
                mail_account_id=account.id,
                source="gmail",
                external_id="4012345678",
                title="Senior AI Engineer",
                company="NovaTech AI",
            )
        )
        db.commit()

        response = api_user1.delete(f"/api/v1/integrations/accounts/{account.id}")
        assert response.status_code == 200
        db.refresh(account)
        assert account.status == ConnectionStatus.DISCONNECTED.value
        assert account.access_token_encrypted is None
        assert account.refresh_token_encrypted is None
        assert account.token_cache_encrypted is None
        assert db.query(Job).filter(Job.user_id == user1.id).count() == 1

        # Purge only works once disconnected, and keeps the jobs.
        assert api_user1.delete(f"/api/v1/integrations/accounts/{account.id}/purge").status_code == 200
        assert db.query(Job).filter(Job.user_id == user1.id).count() == 1

    def test_reconnect_returns_authorization_url(self, api_user1, db, monkeypatch, fake_providers):
        factory, _ = fake_providers(gmail=FakeProviderState())
        monkeypatch.setattr(
            "app.services.oauth_service.ClientFactory", lambda *a, **k: factory
        )
        save_gmail_client(api_user1)
        account = self._link(api_user1, factory, db)

        response = api_user1.post(f"/api/v1/integrations/accounts/{account.id}/reconnect")
        assert response.status_code == 200
        assert response.json()["account_id"] == str(account.id)
        assert "authorization_url" in response.json()

    def test_account_endpoints_are_owner_scoped(self, api_user1, api_user2, db, monkeypatch, fake_providers):
        factory, _ = fake_providers(gmail=FakeProviderState())
        monkeypatch.setattr(
            "app.services.oauth_service.ClientFactory", lambda *a, **k: factory
        )
        save_gmail_client(api_user1)
        account = self._link(api_user1, factory, db)

        assert api_user2.post(f"/api/v1/integrations/accounts/{account.id}/test").status_code == 404
        assert api_user2.patch(f"/api/v1/integrations/accounts/{account.id}", json={}).status_code == 404
        assert api_user2.post(f"/api/v1/integrations/accounts/{account.id}/reconnect").status_code == 404
        assert api_user2.delete(f"/api/v1/integrations/accounts/{account.id}").status_code == 404
        assert api_user1.get("/api/v1/integrations/accounts").json()[0]["id"] == str(account.id)
        assert api_user2.get("/api/v1/integrations/accounts").json() == []

    # --- helper ---------------------------------------------------------
    @staticmethod
    def _link(api, factory, db):
        from app.models.mail_account import MailAccount

        api.post("/api/v1/integrations/gmail/connect")
        client = factory.clients["gmail"]
        response = api.get(
            f"/api/v1/integrations/gmail/callback?code=c&state={client.last_state}",
            follow_redirects=False,
        )
        assert "oauth=success" in response.headers["location"], response.headers
        db.expire_all()
        return (
            db.query(MailAccount)
            .order_by(MailAccount.created_at.desc())
            .first()
        )
