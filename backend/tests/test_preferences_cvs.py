"""Preferences and CV ownership rules."""

from __future__ import annotations

import io


def test_preferences_are_created_with_defaults(api_user1):
    response = api_user1.get("/api/v1/preferences")
    assert response.status_code == 200
    body = response.json()
    assert body["desired_titles"] == []
    assert body["min_match_score"] == 70
    assert body["notify_telegram"] is True


def test_preferences_update_does_not_leak_between_users(api_user1, api_user2):
    updated = api_user1.put(
        "/api/v1/preferences",
        json={
            "desired_titles": ["AI Engineer", "LLM Engineer"],
            "locations": ["İstanbul"],
            "work_modes": ["remote", "hybrid"],
            "min_match_score": 90,
            "keywords_include": ["Python", "RAG"],
            "keywords_exclude": ["satış"],
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["desired_titles"] == ["AI Engineer", "LLM Engineer"]
    assert body["work_modes"] == ["hybrid", "remote"]
    assert body["min_match_score"] == 90

    other = api_user2.get("/api/v1/preferences").json()
    assert other["desired_titles"] == []
    assert other["min_match_score"] == 70

    # user2 sets its own values, user1 keeps theirs.
    api_user2.put("/api/v1/preferences", json={"min_match_score": 40})
    assert api_user2.get("/api/v1/preferences").json()["min_match_score"] == 40
    assert api_user1.get("/api/v1/preferences").json()["min_match_score"] == 90


def test_invalid_work_mode_is_rejected(api_user1):
    response = api_user1.put("/api/v1/preferences", json={"work_modes": ["uzaydan"]})
    assert response.status_code == 422


def _upload(api, name: str, content: bytes, content_type: str):
    return api.post(
        "/api/v1/cvs",
        files={"file": (name, io.BytesIO(content), content_type)},
    )


def test_cv_upload_and_listing(api_user1):
    response = _upload(api_user1, "cv.pdf", b"%PDF-1.6 ornek cv", "application/pdf")
    assert response.status_code == 201, response.text
    cv = response.json()
    assert cv["filename"] == "cv.pdf"
    assert cv["is_active"] is True
    assert cv["has_extracted_text"] is False  # phase 2 extracts the text

    listing = api_user1.get("/api/v1/cvs")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    download = api_user1.get(f"/api/v1/cvs/{cv['id']}/download")
    assert download.status_code == 200
    assert download.content == b"%PDF-1.6 ornek cv"


def test_second_upload_deactivates_first(api_user1):
    _upload(api_user1, "ilk.txt", b"ilk cv", "text/plain")
    second = _upload(api_user1, "ikinci.txt", b"ikinci cv", "text/plain")
    listing = api_user1.get("/api/v1/cvs").json()
    active = [cv for cv in listing if cv["is_active"]]
    assert len(active) == 1
    assert active[0]["id"] == second.json()["id"]


def test_other_users_cv_is_not_reachable(api_user1, api_user2):
    created = _upload(api_user1, "gizli.txt", b"gizli cv icerigi", "text/plain")
    cv_id = created.json()["id"]

    assert api_user2.get(f"/api/v1/cvs/{cv_id}").status_code == 404
    assert api_user2.get(f"/api/v1/cvs/{cv_id}/download").status_code == 404
    assert api_user2.patch(f"/api/v1/cvs/{cv_id}", json={"is_active": False}).status_code == 404
    assert api_user2.delete(f"/api/v1/cvs/{cv_id}").status_code == 404

    # The owner still sees it untouched.
    assert api_user1.get(f"/api/v1/cvs/{cv_id}").status_code == 200
    assert api_user2.get("/api/v1/cvs").json() == []


def test_unsupported_and_empty_files_are_rejected(api_user1):
    bad_type = _upload(api_user1, "zararli.exe", b"MZ...", "application/x-msdownload")
    assert bad_type.status_code == 422

    empty = _upload(api_user1, "bos.txt", b"", "text/plain")
    assert empty.status_code == 422


def test_cv_delete_removes_record(api_user1):
    created = _upload(api_user1, "sil.txt", b"silinecek", "text/plain")
    cv_id = created.json()["id"]
    assert api_user1.delete(f"/api/v1/cvs/{cv_id}").status_code == 200
    assert api_user1.get(f"/api/v1/cvs/{cv_id}").status_code == 404


def test_profile_update_is_scoped(api_user1, api_user2, user2):
    response = api_user1.patch("/api/v1/me", json={"full_name": "Yeni İsim"})
    assert response.status_code == 200
    assert response.json()["full_name"] == "Yeni İsim"

    # user1 cannot take over user2's e-mail address.
    conflict = api_user1.patch("/api/v1/me", json={"email": user2.email})
    assert conflict.status_code == 409

    assert api_user2.get("/api/v1/me").json()["full_name"] == "Test User Two"
