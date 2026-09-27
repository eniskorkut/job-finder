"""CSRF, rate limiting and authentication requirements of the API."""

from __future__ import annotations

from app.core.config import settings


def test_protected_endpoints_require_session(api):
    for path in (
        "/api/v1/me",
        "/api/v1/me/overview",
        "/api/v1/preferences",
        "/api/v1/cvs",
        "/api/v1/jobs",
        "/api/v1/jobs/stats",
        "/api/v1/integrations",
        "/api/v1/sync/history",
        "/api/v1/sync/status",
        "/api/v1/notifications",
        "/api/v1/auth/invitations",
    ):
        response = api.get(path)
        assert response.status_code == 401, f"{path} korunmuyor"
        assert response.json()["detail"]["code"] == "unauthorized"


def test_user_id_cannot_be_spoofed_via_header(api_user1, user1, user2):
    response = api_user1.get(
        "/api/v1/me",
        headers={
            "X-User-Id": str(user2.id),
            "X-User": user2.username,
            "Authorization": f"Bearer {user2.id}",
        },
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(user1.id)
    assert response.json()["username"] == "testuser1"


def test_csrf_header_is_required_for_mutations(api, user1):
    # Log in without the helper header, by using the raw client underneath.
    client = api._client  # noqa: SLF001 - purposeful in this test
    client.get("/api/v1/auth/csrf")
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": "User1-Parola!2026"},
    )
    assert response.status_code == 200

    missing = client.request("POST", "/api/v1/auth/logout")
    assert missing.status_code == 403
    assert missing.json()["detail"]["code"] == "forbidden"

    wrong = client.request(
        "POST",
        "/api/v1/auth/logout",
        headers={settings.csrf_header_name: "sahte-token"},
    )
    assert wrong.status_code == 403

    ok = client.request(
        "POST",
        "/api/v1/auth/logout",
        headers={settings.csrf_header_name: client.cookies.get(settings.csrf_cookie_name)},
    )
    assert ok.status_code == 200


def test_login_rate_limit_blocks_after_repeated_failures(api, user1, limiter):
    limiter.reset()
    for _ in range(settings.login_rate_limit_attempts):
        response = api.post(
            "/api/v1/auth/login",
            json={"identifier": "testuser1", "password": "yanlis-parola"},
        )
        assert response.status_code == 401

    blocked = api.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": "yanlis-parola"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "rate_limited"

    # Correct password is also blocked while the window is open.
    still_blocked = api.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": "User1-Parola!2026"},
    )
    assert still_blocked.status_code == 429
    limiter.reset()


def test_successful_login_resets_rate_limit_counter(api, user1, limiter):
    limiter.reset()
    api.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": "yanlis-parola"},
    )
    api.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": "User1-Parola!2026"},
    )
    allowed, _ = limiter.check("testclient:testuser1")
    assert allowed is True
    limiter.reset()


def test_session_cookie_is_httponly(api, user1):
    response = api.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": "User1-Parola!2026"},
    )
    cookie_header = " ".join(
        value for key, value in response.headers.items() if key.lower() == "set-cookie"
    )
    assert "httponly" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()


def test_expired_session_is_rejected(api_user1, db):
    api_user1.get("/api/v1/me")
    from datetime import datetime, timedelta, timezone

    from app.models.user import UserSession

    session = db.query(UserSession).one()
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    response = api_user1.get("/api/v1/me")
    assert response.status_code == 401
