"""Phase 1 job endpoints: real listing/filtering over mock jobs, plus isolation."""

from __future__ import annotations

import uuid

from app.seed import DEFAULT_DEMO_PASSWORD


def login_seeded(api, username: str):
    response = api.post(
        "/api/v1/auth/login",
        json={"identifier": username, "password": DEFAULT_DEMO_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return api


def test_mock_jobs_are_visible_only_to_their_owner(api, seeded):
    login_seeded(api, "ai_hunter")
    own = api.get("/api/v1/jobs")
    assert own.status_code == 200
    own_body = own.json()
    titles = [item["title"] for item in own_body["items"]]
    assert "Senior AI Engineer" in titles
    assert "LLM Engineer" in titles
    assert all(item["is_mock"] for item in own_body["items"])
    assert len(titles) == 7

    # A different user does not see any of those jobs.
    api.post("/api/v1/auth/logout")
    login_seeded(api, "data_hunter")
    other = api.get("/api/v1/jobs")
    other_titles = [item["title"] for item in other.json()["items"]]
    assert "Senior AI Engineer" not in other_titles
    assert "Data Analyst" in other_titles


def test_other_users_job_is_not_reachable_even_with_the_uuid(api, seeded):
    login_seeded(api, "ai_hunter")
    victim_job = api.get("/api/v1/jobs?page_size=1").json()["items"][0]
    victim_id = victim_job["id"]

    api.post("/api/v1/auth/logout")
    login_seeded(api, "data_hunter")

    detail = api.get(f"/api/v1/jobs/{victim_id}")
    assert detail.status_code == 404
    assert detail.json()["detail"]["code"] == "not_found"

    patched = api.patch(f"/api/v1/jobs/{victim_id}", json={"status": "saved"})
    assert patched.status_code == 404

    unknown = api.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert unknown.status_code == 404


def test_search_and_filters(api, seeded):
    login_seeded(api, "ai_hunter")

    search = api.get("/api/v1/jobs", params={"search": "llm"})
    assert search.status_code == 200
    titles = [item["title"] for item in search.json()["items"]]
    assert "LLM Engineer" in titles
    assert "Computer Vision Engineer" not in titles

    company = api.get("/api/v1/jobs", params={"company": "NovaTech AI"})
    assert company.json()["total"] == 1

    high_score = api.get("/api/v1/jobs", params={"min_score": 85})
    scores = [item["match"]["score"] for item in high_score.json()["items"]]
    assert scores and all(score >= 85 for score in scores)

    remote = api.get("/api/v1/jobs", params={"work_mode": "remote"})
    modes = {item["work_mode"] for item in remote.json()["items"]}
    assert modes == {"remote"}

    saved = api.get("/api/v1/jobs", params={"status": "saved"})
    assert saved.json()["total"] == 1
    assert saved.json()["items"][0]["title"] == "LLM Engineer"

    sorted_by_score = api.get("/api/v1/jobs", params={"sort": "score"})
    scores_desc = [item["match"]["score"] for item in sorted_by_score.json()["items"]]
    assert scores_desc == sorted(scores_desc, reverse=True)

    filtered_options = api.get("/api/v1/jobs/filters")
    assert filtered_options.status_code == 200
    assert "NovaTech AI" in filtered_options.json()["companies"]


def test_pagination(api, seeded):
    login_seeded(api, "ai_hunter")
    first = api.get("/api/v1/jobs", params={"page": 1, "page_size": 3})
    body = first.json()
    assert body["total"] == 7
    assert body["pages"] == 3
    assert len(body["items"]) == 3

    second = api.get("/api/v1/jobs", params={"page": 2, "page_size": 3})
    first_ids = {item["id"] for item in body["items"]}
    second_ids = {item["id"] for item in second.json()["items"]}
    assert not (first_ids & second_ids)


def test_job_detail_and_status_update(api, seeded):
    login_seeded(api, "data_hunter")
    listing = api.get("/api/v1/jobs", params={"search": "Backend Developer"})
    job = listing.json()["items"][0]

    detail = api.get(f"/api/v1/jobs/{job['id']}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["description"]
    assert payload["match"]["rationale"]
    assert payload["match"]["matched_skills"]

    # Opening the detail marks a "new" match as viewed.
    refreshed = api.get(f"/api/v1/jobs/{job['id']}")
    assert refreshed.json()["match"]["status"] in {"viewed", "saved"}

    updated = api.patch(f"/api/v1/jobs/{job['id']}", json={"status": "dismissed"})
    assert updated.status_code == 200
    assert updated.json()["match"]["status"] == "dismissed"

    dismissed = api.get("/api/v1/jobs", params={"status": "dismissed"})
    assert dismissed.json()["total"] >= 1


def test_stats_are_scoped_per_user(api, seeded):
    login_seeded(api, "ai_hunter")
    stats = api.get("/api/v1/jobs/stats").json()
    assert stats["total_jobs"] == 7
    assert stats["mock_jobs"] == 7
    assert stats["high_match_threshold"] == 75
    assert stats["high_match_jobs"] == 4  # 92, 88, 84, 78
    assert stats["saved_jobs"] == 1
    assert stats["dismissed_jobs"] == 1
    assert stats["average_score"] is not None

    api.post("/api/v1/auth/logout")
    login_seeded(api, "data_hunter")
    other = api.get("/api/v1/jobs/stats").json()
    assert other["total_jobs"] == 6
    assert other["high_match_threshold"] == 65
    assert other["high_match_jobs"] == 3  # 90, 86, 74


def test_overview_matches_own_data(api, seeded):
    login_seeded(api, "ai_hunter")
    overview = api.get("/api/v1/me/overview").json()
    assert overview["total_jobs"] == 7
    assert overview["has_mock_data"] is True
    assert overview["has_active_cv"] is True
    assert overview["sync_available"] is True
    providers = {item["provider"]: item for item in overview["integrations"]}
    assert providers["gmail"]["status"] == "disconnected"
    assert providers["gmail"]["available"] is True
    assert providers["gmail"]["account_count"] == 1
    assert providers["telegram"]["available"] is False


def test_sync_history_is_scoped_per_user(api, seeded):
    login_seeded(api, "ai_hunter")
    history = api.get("/api/v1/sync/history").json()
    assert history["total"] == 3
    assert all(item["is_mock"] for item in history["items"])

    api.post("/api/v1/auth/logout")
    login_seeded(api, "data_hunter")
    other = api.get("/api/v1/sync/history").json()
    assert other["total"] == 3
    assert {item["source"] for item in other["items"]} == {"outlook"}


def test_notifications_are_scoped_per_user(api, seeded):
    login_seeded(api, "ai_hunter")
    notifications = api.get("/api/v1/notifications").json()
    assert notifications["total"] >= 1
    assert all(item["status"] == "skipped" for item in notifications["items"])
    assert all(item["is_mock"] for item in notifications["items"])
