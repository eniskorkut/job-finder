"""Per-user Telegram integration and idempotent notifications."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from app.core.crypto import decrypt_secret
from app.integrations.telegram import TelegramError
from app.models.enums import (
    ConnectionStatus,
    ErrorClass,
    NotificationStatus,
    SyncJobStatus,
)
from app.models.job import Job, JobMatch
from app.models.notification import NotificationHistory
from app.models.sync_job import SyncJob
from app.models.telegram import TelegramIntegration
from app.repositories.integrations import TelegramRepository
from app.services.notification_service import NotificationRunner, NotificationService
from app.services.telegram_service import TelegramConfigService
from tests.fakes_phase3 import (
    FakeTelegramState,
    fake_telegram_factory,
    update_with_message,
)

CHAT_ID = "424242"


def configure_telegram(db, user, state: FakeTelegramState, *, chat_id: str = CHAT_ID):
    service = TelegramConfigService(db, client_factory=fake_telegram_factory(state))
    status = asyncio.run(
        service.save_config(user, bot_token=state.token, chat_id=chat_id)
    )
    db.commit()
    return status


def make_match(
    db,
    user,
    *,
    score: int = 88,
    title: str = "AI Engineer",
    notified: bool = False,
) -> JobMatch:
    job = Job(
        user_id=user.id,
        source="gmail",
        external_id=f"e2e-{uuid.uuid4().hex[:10]}",
        title=title,
        company="NovaTech AI",
        location="İstanbul, Türkiye",
        work_mode="hybrid",
        description="Python, FastAPI, RAG bekliyoruz.",
        url="https://www.linkedin.com/jobs/view/1",
        is_mock=False,
    )
    db.add(job)
    db.flush()
    match = JobMatch(
        user_id=user.id,
        job_id=job.id,
        score=score,
        confidence=80,
        rationale="CV gereksinimleri karşılıyor.",
        matched_skills=["Python", "FastAPI"],
        missing_skills=["Kubernetes"],
        analysis_status="completed",
        cv_checksum="checksum-a",
        notified_at=datetime.now(timezone.utc) if notified else None,
    )
    db.add(match)
    db.commit()
    return match


def run_notify(db, job_id: uuid.UUID, state: FakeTelegramState):
    """Run a notify job the way the worker does, including job bookkeeping."""
    from app.db.session import SessionLocal
    from app.models.sync_job import SyncJob as _SyncJob
    from app.repositories.sync_jobs import SyncJobRepository

    runner = NotificationRunner(client_factory=fake_telegram_factory(state))
    outcome = asyncio.run(runner.run(job_id))
    with SessionLocal() as session:
        job = session.get(_SyncJob, job_id)
        if job is not None:
            SyncJobRepository(session).finish(job, outcome.status, error=outcome.error_message)
        session.commit()
    db.expire_all()
    return outcome


def queue_notify(db, user) -> SyncJob | None:
    service = NotificationService(db)
    job = service.enqueue(user)
    db.commit()
    return job


class TestTelegramConfig:
    def test_config_is_verified_and_masked(self, db, user1):
        state = FakeTelegramState()
        state.register_chat(CHAT_ID)
        status = configure_telegram(db, user1, state)

        assert status["status"] == ConnectionStatus.CONNECTED.value
        assert status["bot_username"] == "jobhunter_test_bot"
        assert status["chat_id"] == CHAT_ID
        # Only the tail of the token is ever shown (like "****alue").
        assert status["token_hint"].endswith("alue")
        assert "123456789" not in status["token_hint"]
        assert state.token not in str(status)

        integration = TelegramRepository(db).get_for_user(user1.id)
        assert integration.bot_token_encrypted != state.token
        assert decrypt_secret(integration.bot_token_encrypted) == state.token

    def test_api_never_returns_the_raw_token(self, api_user1, db, user1, monkeypatch):
        state = FakeTelegramState()
        state.register_chat(CHAT_ID)
        monkeypatch.setattr(
            "app.services.telegram_service.default_telegram_factory",
            fake_telegram_factory(state),
        )
        response = api_user1.post(
            "/api/v1/integrations/telegram/config",
            json={"bot_token": state.token, "chat_id": CHAT_ID},
        )
        assert response.status_code == 200, response.text
        assert state.token not in response.text

        listing = api_user1.get("/api/v1/integrations")
        assert state.token not in listing.text
        telegram = next(
            item for item in listing.json()["integrations"] if item["provider"] == "telegram"
        )
        assert telegram["status"] == "connected"
        assert telegram["capabilities"]["bot_username"] == "jobhunter_test_bot"

    def test_invalid_token_is_rejected_without_saving(
        self, api_user1, db, user1, monkeypatch
    ):
        state = FakeTelegramState()
        monkeypatch.setattr(
            "app.services.telegram_service.default_telegram_factory",
            fake_telegram_factory(state),
        )
        response = api_user1.post(
            "/api/v1/integrations/telegram/config", json={"bot_token": "bozuk"}
        )
        assert response.status_code == 422
        integration = TelegramRepository(db).get_for_user(user1.id)
        assert integration is None or integration.bot_token_encrypted is None

    def test_invalid_chat_is_rejected(self, api_user1, db, user1, monkeypatch):
        state = FakeTelegramState()
        monkeypatch.setattr(
            "app.services.telegram_service.default_telegram_factory",
            fake_telegram_factory(state),
        )
        response = api_user1.post(
            "/api/v1/integrations/telegram/config",
            json={"bot_token": state.token, "chat_id": "999999"},
        )
        assert response.status_code == 422
        assert "Chat ID" in response.json()["detail"]["message"]

    def test_detect_chat_returns_candidates(self, api_user1, db, user1, monkeypatch):
        state = FakeTelegramState()
        state.updates = [update_with_message(CHAT_ID)]
        monkeypatch.setattr(
            "app.services.telegram_service.default_telegram_factory",
            fake_telegram_factory(state),
        )
        response = api_user1.post(
            "/api/v1/integrations/telegram/detect-chat",
            json={"bot_token": state.token},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["suggested_chat_id"] == CHAT_ID
        assert body["requires_manual_choice"] is False

    def test_detect_chat_asks_the_user_when_ambiguous(
        self, api_user1, db, user1, monkeypatch
    ):
        state = FakeTelegramState()
        state.updates = [
            update_with_message(CHAT_ID, message_id=1),
            update_with_message("777777", title="Başka Kişi", message_id=2),
        ]
        monkeypatch.setattr(
            "app.services.telegram_service.default_telegram_factory",
            fake_telegram_factory(state),
        )
        response = api_user1.post(
            "/api/v1/integrations/telegram/detect-chat",
            json={"bot_token": state.token},
        )
        body = response.json()
        assert body["requires_manual_choice"] is True
        assert body["suggested_chat_id"] is None
        assert len(body["candidates"]) == 2

    def test_test_message_and_disconnect(self, api_user1, db, user1, monkeypatch):
        state = FakeTelegramState()
        state.register_chat(CHAT_ID)
        monkeypatch.setattr(
            "app.services.telegram_service.default_telegram_factory",
            fake_telegram_factory(state),
        )
        api_user1.post(
            "/api/v1/integrations/telegram/config",
            json={"bot_token": state.token, "chat_id": CHAT_ID},
        )
        sent = api_user1.post("/api/v1/notifications/test").json()
        assert sent["ok"] is True
        assert state.sent[-1]["chat_id"] == CHAT_ID

        removed = api_user1.delete("/api/v1/integrations/telegram")
        assert removed.status_code == 200
        integration = TelegramRepository(db).get_for_user(user1.id)
        assert integration.bot_token_encrypted is None
        assert api_user1.post("/api/v1/notifications/test").status_code == 422

    def test_status_is_owner_scoped(self, api_user1, api_user2, db, user1):
        state = FakeTelegramState()
        state.register_chat(CHAT_ID)
        configure_telegram(db, user1, state)

        status_b = api_user2.get("/api/v1/integrations/telegram/status").json()
        assert status_b["status"] == ConnectionStatus.DISCONNECTED.value
        assert status_b["chat_id"] is None
        assert status_b["has_token"] is False


class TestNotificationDispatch:
    def test_successful_delivery_is_recorded_and_idempotent(
        self, db, user1, telegram_ready
    ):
        state = telegram_ready
        match = make_match(db, user1, score=88)
        job = queue_notify(db, user1)
        assert job is not None and job.kind == "notify"

        outcome = run_notify(db, job.id, state)
        assert outcome.sent == 1
        assert len(state.sent) == 1
        assert "%88" in state.sent[0]["text"]

        db.expire_all()
        history = db.query(NotificationHistory).one()
        assert history.status == NotificationStatus.SENT.value
        assert history.dedupe_key == f"telegram:match:{match.id}"
        assert history.provider_message_id

        refreshed = db.query(JobMatch).one()
        assert refreshed.notified_at is not None
        assert refreshed.status == "notified"

        # Nothing eligible is left, so no second job is queued.
        assert queue_notify(db, user1) is None

    def test_second_run_does_not_resend(self, db, user1, telegram_ready):
        state = telegram_ready
        make_match(db, user1, score=90)
        job = queue_notify(db, user1)
        run_notify(db, job.id, state)
        assert len(state.sent) == 1

        # A forced notify job for the same match must skip it.
        service = NotificationService(db)
        forced = service.queue.create(
            user_id=user1.id,
            kind="notify",
            trigger="manual",
            payload={"match_ids": [str(db.query(JobMatch).one().id)]},
        )
        db.commit()
        outcome = run_notify(db, forced.id, state)
        assert outcome.sent == 0
        assert len(state.sent) == 1

    def test_below_threshold_is_not_notified(self, db, user1, telegram_ready):
        state = telegram_ready
        make_match(db, user1, score=40)
        assert queue_notify(db, user1) is None
        assert state.sent == []

    def test_notify_disabled_skips_everything(self, db, user1, telegram_ready):
        from app.repositories.preferences import PreferenceRepository

        preference = PreferenceRepository(db).get_or_create(user1)
        preference.notify_telegram = False
        db.commit()
        make_match(db, user1, score=95)
        assert queue_notify(db, user1) is None

    def test_disconnected_telegram_reports_skipped(self, db, user1):
        make_match(db, user1, score=95)
        job = NotificationService(db).queue.create(
            user_id=user1.id, kind="notify", trigger="manual", payload={"match_ids": []}
        )
        db.commit()
        outcome = run_notify(db, job.id, FakeTelegramState())
        assert outcome.skipped >= 1
        assert outcome.error_message and "Telegram" in outcome.error_message

    def test_failure_is_retryable_and_then_succeeds(self, db, user1, telegram_ready):
        state = telegram_ready
        make_match(db, user1, score=91)
        state.send_error = TelegramError(
            "rate_limited", error_class=ErrorClass.RATE_LIMIT, retry_after=1
        )
        job = queue_notify(db, user1)
        outcome = run_notify(db, job.id, state)
        assert outcome.failed == 1
        assert state.sent == []

        db.expire_all()
        failed = db.query(NotificationHistory).one()
        assert failed.status == NotificationStatus.FAILED.value
        assert failed.error_class == ErrorClass.RATE_LIMIT.value
        assert failed.dedupe_key is None  # not delivered -> retryable

        # Telegram recovers; the next dispatch delivers it.
        state.send_error = None
        job2 = queue_notify(db, user1)
        assert job2 is not None
        outcome2 = run_notify(db, job2.id, state)
        assert outcome2.sent == 1
        db.expire_all()
        assert db.query(NotificationHistory).one().status == NotificationStatus.SENT.value

    def test_bot_blocked_marks_the_integration_for_reauth(self, db, user1, telegram_ready):
        state = telegram_ready
        make_match(db, user1, score=90)
        state.send_error = TelegramError("bot_blocked", error_class=ErrorClass.AUTH)
        job = queue_notify(db, user1)
        run_notify(db, job.id, state)

        db.expire_all()
        integration = TelegramRepository(db).get_for_user(user1.id)
        assert integration.status == ConnectionStatus.NEEDS_REAUTH.value
        assert integration.last_error_class == ErrorClass.AUTH.value
        # Scoring is untouched by a broken bot.
        assert db.query(JobMatch).one().analysis_status == "completed"

    def test_message_is_html_escaped(self, db, user1, telegram_ready):
        state = telegram_ready
        make_match(db, user1, score=90, title="AI <script> Engineer")
        job = queue_notify(db, user1)
        run_notify(db, job.id, state)
        assert "&lt;script&gt;" in state.sent[0]["text"]

    def test_isolation_between_users(self, db, user1, user2, telegram_ready):
        state = telegram_ready
        match_a = make_match(db, user1, score=95, title="A Engineer")
        match_b = make_match(db, user2, score=95, title="B Engineer")

        job = queue_notify(db, user1)
        run_notify(db, job.id, state)

        db.expire_all()
        assert db.query(NotificationHistory).filter_by(job_match_id=match_a.id).count() == 1
        assert db.query(NotificationHistory).filter_by(job_match_id=match_b.id).count() == 0
        assert all("A Engineer" in message["text"] for message in state.sent)

    def test_summary_counts_only_the_owner(self, api_user1, api_user2, db, user1, user2, telegram_ready):
        state = telegram_ready
        make_match(db, user1, score=90)
        job = queue_notify(db, user1)
        run_notify(db, job.id, state)

        summary = api_user1.get("/api/v1/notifications/summary").json()
        assert summary["sent"] == 1
        assert summary["threshold"] == 70

        other = api_user2.get("/api/v1/notifications/summary").json()
        assert other["sent"] == 0
        assert other["telegram_ready"] is False
        assert api_user2.get("/api/v1/notifications").json()["total"] == 0

    def test_dispatch_endpoint_queues_and_reports(self, api_user1, db, user1, telegram_ready):
        make_match(db, user1, score=88)
        response = api_user1.post("/api/v1/notifications/dispatch")
        assert response.status_code == 202
        body = response.json()
        assert body["queued"] is True
        assert body["total"] == 1
        assert db.get(SyncJob, uuid.UUID(body["job_id"])).kind == "notify"

        # Second call while the job is still queued: the same job is reported
        # instead of creating a duplicate delivery job.
        again = api_user1.post("/api/v1/notifications/dispatch")
        assert again.status_code == 202
        assert again.json()["queued"] is True
        assert again.json()["job_id"] == body["job_id"]

        # After the worker delivered it, a new dispatch finds nothing to do.
        run_notify(db, uuid.UUID(body["job_id"]), telegram_ready)
        after = api_user1.post("/api/v1/notifications/dispatch")
        assert after.status_code == 202
        assert after.json()["queued"] is False
