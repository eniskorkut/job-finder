"""Invitation lifecycle: creation rules, single use, expiry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.invitation_service import InvitationService

from tests.conftest import USER1_PASSWORD


def test_owner_creates_invitation_and_member_accepts(api_user1, db):
    created = api_user1.post(
        "/api/v1/auth/invitations", json={"email": "davetli@example.com"}
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["status"] == "pending"
    assert payload["invite_url"].startswith("http://localhost:3000/invite/")
    token = payload["invite_url"].rsplit("/", 1)[-1]

    inspection = api_user1.get(f"/api/v1/auth/invitations/{token}/inspect")
    assert inspection.status_code == 200
    assert inspection.json()["is_valid"] is True
    assert inspection.json()["email"] == "davetli@example.com"

    accepted = api_user1.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "username": "davetli",
            "password": "Davetli-Parola!2026",
            "full_name": "Davetli Kullanıcı",
        },
    )
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()
    assert body["user"]["username"] == "davetli"
    assert body["user"]["role"] == "member"

    # New account gets its own preferences row.
    preferences = api_user1.get("/api/v1/preferences")
    assert preferences.status_code == 200


def test_invitation_is_single_use(api, api_user1, db):
    created = api_user1.post(
        "/api/v1/auth/invitations", json={"email": "tek@example.com"}
    )
    token = created.json()["invite_url"].rsplit("/", 1)[-1]

    first = api.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "username": "tek1", "password": "Tek-Kullanici!2026"},
    )
    assert first.status_code == 201

    second = api.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "username": "tek2", "password": "Tek-Kullanici!2026"},
    )
    assert second.status_code == 422
    assert "kullanılmış" in second.json()["detail"]["message"]

    inspection = api.get(f"/api/v1/auth/invitations/{token}/inspect")
    assert inspection.json()["is_valid"] is False


def test_expired_invitation_is_rejected(api, api_user1, db):
    created = api_user1.post(
        "/api/v1/auth/invitations", json={"email": "suresi@example.com"}
    )
    token = created.json()["invite_url"].rsplit("/", 1)[-1]

    service = InvitationService(db)
    invitation = service.invitations.get_by_token(token)
    invitation.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    inspection = api.get(f"/api/v1/auth/invitations/{token}/inspect")
    assert inspection.status_code == 200
    assert inspection.json()["is_valid"] is False
    assert "süresi dolmuş" in inspection.json()["message"]

    rejected = api.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "username": "gec", "password": "Gec-Kullanici!2026"},
    )
    assert rejected.status_code == 422


def test_member_cannot_invite_or_list_users(api_user2):
    created = api_user2.post(
        "/api/v1/auth/invitations", json={"email": "olmaz@example.com"}
    )
    assert created.status_code == 403
    assert api_user2.get("/api/v1/auth/invitations").status_code == 403
    assert api_user2.get("/api/v1/auth/users").status_code == 403


def test_owner_can_list_and_revoke_invitations(api_user1):
    created = api_user1.post(
        "/api/v1/auth/invitations", json={"email": "iptal@example.com"}
    )
    invitation_id = created.json()["id"]

    listing = api_user1.get("/api/v1/auth/invitations")
    assert listing.status_code == 200
    assert any(item["id"] == invitation_id for item in listing.json())

    revoked = api_user1.delete(f"/api/v1/auth/invitations/{invitation_id}")
    assert revoked.status_code == 200

    after = api_user1.get("/api/v1/auth/invitations")
    assert all(item["id"] != invitation_id for item in after.json())


def test_invitation_email_cannot_be_swapped(api, api_user1):
    created = api_user1.post(
        "/api/v1/auth/invitations", json={"email": "hedef@example.com"}
    )
    token = created.json()["invite_url"].rsplit("/", 1)[-1]

    response = api.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "username": "baskasi",
            "email": "baskasi@example.com",
            "password": "Baskasi-Parola!2026",
        },
    )
    assert response.status_code == 422


def test_invitation_for_existing_email_is_rejected(api_user1, user2):
    response = api_user1.post(
        "/api/v1/auth/invitations", json={"email": "user2@example.com"}
    )
    assert response.status_code == 409


def test_accepted_invitation_creates_isolated_account(api, seeded):
    """The invited user lands in a fresh, empty workspace."""
    from app.seed import DEFAULT_DEMO_PASSWORD

    owner_login = api.post(
        "/api/v1/auth/login",
        json={"identifier": "ai_hunter", "password": DEFAULT_DEMO_PASSWORD},
    )
    assert owner_login.status_code == 200
    assert api.get("/api/v1/jobs").json()["total"] == 7

    created = api.post(
        "/api/v1/auth/invitations", json={"email": "izole@example.com"}
    )
    token = created.json()["invite_url"].rsplit("/", 1)[-1]

    accepted = api.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "username": "izole", "password": "Izole-Parola!2026"},
    )
    assert accepted.status_code == 201, accepted.text

    # The client now holds the new member's session: owner data is invisible.
    jobs = api.get("/api/v1/jobs")
    assert jobs.status_code == 200
    assert jobs.json()["total"] == 0
    assert api.get("/api/v1/preferences").json()["desired_titles"] == []
    assert api.get("/api/v1/sync/history").json()["total"] == 0

    # Owner data is still intact after logging back in.
    api.post(
        "/api/v1/auth/login",
        json={"identifier": "ai_hunter", "password": DEFAULT_DEMO_PASSWORD},
    )
    assert api.get("/api/v1/jobs").json()["total"] == 7


def test_bogus_invitation_token_is_rejected(api):
    response = api.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": "bu-token-tamamen-uyudurma",
            "username": "uyudurma",
            "password": "Uydurma-Parola!2026",
        },
    )
    assert response.status_code == 422
    assert "geçersiz" in response.json()["detail"]["message"]
