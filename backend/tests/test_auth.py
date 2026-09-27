"""User creation, session and password behaviour."""

from __future__ import annotations

from app.core import errors
from app.core.security import hash_password, verify_password
from app.services.user_service import UserService

from tests.conftest import USER1_PASSWORD


def test_user_service_creates_user_with_argon2id_hash(db):
    user = UserService(db).create_user(
        username="yeni", email="yeni@example.com", password=USER1_PASSWORD
    )
    db.commit()
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != USER1_PASSWORD
    assert verify_password(USER1_PASSWORD, user.password_hash)


def test_duplicate_username_and_email_are_rejected(db):
    service = UserService(db)
    service.create_user(username="ayni", email="ayni@example.com", password=USER1_PASSWORD)
    db.commit()

    for kwargs in (
        {"username": "ayni", "email": "baska@example.com"},
        {"username": "baska", "email": "ayni@example.com"},
    ):
        try:
            service.create_user(password=USER1_PASSWORD, **kwargs)
        except errors.AppError as exc:
            assert exc.status_code == 409
        else:  # pragma: no cover - should not happen
            raise AssertionError("Çakışan kayıt kabul edildi")
    db.rollback()


def test_only_one_owner_can_exist(db):
    service = UserService(db)
    service.create_user(
        username="owner", email="owner@example.com", password=USER1_PASSWORD, make_owner=True
    )
    db.commit()
    try:
        service.create_user(
            username="owner2",
            email="owner2@example.com",
            password=USER1_PASSWORD,
            make_owner=True,
        )
    except errors.AppError as exc:
        assert exc.detail["code"] == "conflict"
    else:  # pragma: no cover
        raise AssertionError("İkinci owner kabul edildi")
    db.rollback()


def test_login_and_logout_flow(api, user1):
    response = api.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": USER1_PASSWORD},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["username"] == "testuser1"
    assert body["user"]["role"] == "owner"
    assert body["csrf_token"]
    assert api.cookies.get("jh_session")

    session = api.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json()["user"]["email"] == "user1@example.com"

    logout = api.post("/api/v1/auth/logout")
    assert logout.status_code == 200
    assert api.get("/api/v1/auth/session").status_code == 401


def test_login_with_email_identifier_works(api, user1):
    response = api.post(
        "/api/v1/auth/login",
        json={"identifier": "user1@example.com", "password": USER1_PASSWORD},
    )
    assert response.status_code == 200


def test_login_with_wrong_password_fails(api, user1):
    response = api.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": "yanlis-parola"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_login_with_unknown_user_fails(api):
    response = api.post(
        "/api/v1/auth/login",
        json={"identifier": "yok-boyle-biri", "password": "herhangi-bir-sey"},
    )
    assert response.status_code == 401


def test_inactive_user_cannot_login(api, db, user2):
    user2.is_active = False
    db.commit()
    response = api.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser2", "password": "User2-Parola!2026"},
    )
    assert response.status_code == 403


def test_change_password_requires_current_password(api_user1):
    response = api_user1.post(
        "/api/v1/auth/password",
        json={"current_password": "yanlis", "new_password": "Yepyeni-Parola!2026"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_error"


def test_change_password_rotates_session(api_user1):
    response = api_user1.post(
        "/api/v1/auth/password",
        json={"current_password": USER1_PASSWORD, "new_password": "Yepyeni-Parola!2026"},
    )
    assert response.status_code == 200, response.text
    assert api_user1.get("/api/v1/me").status_code == 200

    # Old password no longer works, new one does.
    fresh_response = api_user1.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": USER1_PASSWORD},
    )
    assert fresh_response.status_code == 401
    new_response = api_user1.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": "Yepyeni-Parola!2026"},
    )
    assert new_response.status_code == 200


def test_weak_password_is_rejected(api, user1):
    response = api.post(
        "/api/v1/auth/login",
        json={"identifier": "testuser1", "password": USER1_PASSWORD},
    )
    assert response.status_code == 200
    change = api.post(
        "/api/v1/auth/password",
        json={"current_password": USER1_PASSWORD, "new_password": "kisa"},
    )
    assert change.status_code == 422


def test_password_hash_verification_helpers():
    hashed = hash_password("Gizli-Parola!2026")
    assert verify_password("Gizli-Parola!2026", hashed)
    assert not verify_password("baska-parola", hashed)
    assert not verify_password("Gizli-Parola!2026", "bozuk-hash-degeri")
