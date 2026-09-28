"""End-to-end: two users, same LinkedIn alert, different CVs and thresholds.

USER A: CV with the A marker -> fake LLM scores 88 -> threshold 70 -> Telegram A (sent)
USER B: CV with the B marker -> fake LLM scores 52 -> threshold 70 -> no message

The pipeline runs through the real durable queue (mail_scan -> scoring -> notify)
with fake Gmail / LLM / Telegram providers, and every cross-user access is checked.
"""

from __future__ import annotations

import asyncio
import uuid

from app.core.crypto import encrypt_secret
from app.models.enums import ConnectionStatus, SyncJobStatus
from app.models.job import Job, JobMatch
from app.models.notification import NotificationHistory
from app.models.sync_job import SyncJob
from app.models.telegram import TelegramIntegration
from app.models.user import User
from app.repositories.jobs import MailAccountRepository
from app.repositories.preferences import PreferenceRepository
from app.repositories.integrations import TelegramRepository
from app.services.sync_job_service import SyncRunner
from tests.conftest import add_oauth_client, add_mail_account, run_scan
from tests.fakes import FakeClientFactory, FakeMailProviderClient, FakeProviderState, gmail_page
from tests.fakes_phase3 import (
    DEFAULT_PROFILE,
    FakeLlmState,
    FakeTelegramClient,
    FakeTelegramState,
    fake_llm_factory,
)
from tests.fixtures import emails
from tests.test_scan_pipeline import WINDOW_NOW, message_map, v1_message

TOKEN_A = "111111111:FAKE-token-user-a-aaaaaaaa"
TOKEN_B = "222222222:FAKE-token-user-b-bbbbbbbb"
CHAT_A = "100001"
CHAT_B = "200002"


def add_cv_with_marker(db, user, marker: str):
    from app.models.cv import CV

    text = (
        f"{marker} - AI Engineer\n"
        "6 yıl deneyim: Python, FastAPI, PyTorch, RAG.\n"
        "Telefon: +90 (532) 000 00 00\nE-posta: kisi@example.com\n"
    )
    cv = CV(
        user_id=user.id,
        filename=f"cv-{marker.lower()}.pdf",
        content_type="application/pdf",
        size_bytes=len(text),
        storage_path=f"{user.id}/cv.pdf",
        checksum=f"checksum-{marker.lower()}",
        extracted_text=text,
        extraction_status="ok",
        is_active=True,
    )
    db.add(cv)
    db.commit()
    return cv


def configure_telegram(db, user, token: str, chat_id: str) -> TelegramIntegration:
    integration = TelegramRepository(db).get_or_create(user.id)
    integration.bot_token_encrypted = encrypt_secret(token)
    integration.chat_id = chat_id
    integration.username = f"bot_{chat_id}"
    integration.status = ConnectionStatus.CONNECTED.value
    db.commit()
    return integration


def prepare_user(db, user, marker: str, token: str, chat_id: str, *, threshold: int = 70):
    add_cv_with_marker(db, user, marker)
    add_oauth_client(db, user, "gmail")
    account = add_mail_account(
        db, user, "gmail", email_address=f"{marker.lower()}@gmail.example.com"
    )
    configure_telegram(db, user, token, chat_id)

    preference = PreferenceRepository(db).get_or_create(user)
    preference.min_match_score = threshold
    preference.notify_telegram = True
    preference.daily_scan_enabled = False
    db.commit()
    return account


def routing_llm_factory():
    """One fake LLM for two users: the score depends on the CV marker."""

    def profile_resolver(cv_text: str) -> dict:
        marker = "A-Marker" if "A-Marker" in cv_text else "B-Marker"
        return {**DEFAULT_PROFILE, "skills": [marker, "Python", "FastAPI"]}

    def score_resolver(profile: dict, title: str) -> int:
        return 88 if "A-Marker" in (profile.get("skills") or []) else 52

    state = FakeLlmState(
        profile_resolver=profile_resolver, score_resolver=score_resolver
    )
    return fake_llm_factory(state), state


def telegram_factory(states: dict[str, FakeTelegramState]):
    return lambda token: FakeTelegramClient(token, states[token])


def drain_queue(runner: SyncRunner, *, max_cycles: int = 12) -> int:
    processed = 0
    for _ in range(max_cycles):
        cycles = asyncio.run(runner.run_forever(once=True))
        processed += cycles
        if cycles == 0:
            break
    return processed


def test_two_user_pipeline_end_to_end(db, user1, user2, fake_providers):
    # --- identities -----------------------------------------------------
    account_a = prepare_user(db, user1, "A-Marker", TOKEN_A, CHAT_A)
    account_b = prepare_user(db, user2, "B-Marker", TOKEN_B, CHAT_B)

    telegram_states = {
        TOKEN_A: FakeTelegramState(token=TOKEN_A),
        TOKEN_B: FakeTelegramState(token=TOKEN_B),
    }
    telegram_states[TOKEN_A].register_chat(CHAT_A, title="Kullanıcı A")
    telegram_states[TOKEN_B].register_chat(CHAT_B, title="Kullanıcı B")

    # --- the same LinkedIn alert reaches both mailboxes -----------------
    alert_a = v1_message("msg-a")
    alert_b = emails.raw_message(
        external_id="msg-b",
        subject="NovaTech AI için yeni iş ilanı",
        html=emails.HTML_TABLE_V1,
    )
    provider_factory = FakeClientFactory(
        {
            "gmail": FakeMailProviderClient(
                provider="gmail",
                state=FakeProviderState(
                    messages=message_map(alert_a),
                    pages=[gmail_page(["msg-a"], checkpoint="h-a")],
                ),
            )
        }
    )

    # --- phase 1: user A scans, then user B scans -----------------------
    run_scan(db, user1, account_a, provider_factory)
    provider_factory.clients["gmail"].reset_pages(
        [gmail_page(["msg-b"], checkpoint="h-b")]
    )
    provider_factory.clients["gmail"].state.messages = message_map(alert_b)
    run_scan(db, user2, account_b, provider_factory)

    db.expire_all()
    jobs_a = db.query(Job).filter(Job.user_id == user1.id).all()
    jobs_b = db.query(Job).filter(Job.user_id == user2.id).all()
    assert len(jobs_a) == 2 and len(jobs_b) == 2
    # Same external posting, but two independent rows (never merged across users).
    assert {job.external_id for job in jobs_a} == {job.external_id for job in jobs_b}
    assert {job.id for job in jobs_a}.isdisjoint({job.id for job in jobs_b})

    # --- phase 2: scoring + delivery through the real queue -------------
    llm_factory, llm_state = routing_llm_factory()
    runner = SyncRunner(
        worker_id="e2e-worker",
        client_factory=provider_factory,
        llm_factory=llm_factory,
        telegram_factory=telegram_factory(telegram_states),
        now=WINDOW_NOW,
    )

    # Scoring jobs were already enqueued by the scans above.
    from app.services.notification_service import NotificationService
    from app.services.scoring_service import ScoringService

    for user in (user1, user2):
        ScoringService(db).enqueue_for_new_jobs(user.id)
    db.commit()

    processed = drain_queue(runner)
    # 2 scoring jobs; only user A's score clears the threshold, so 1 notify job.
    assert processed == 3

    # --- assertions: A notified, B not ----------------------------------
    db.expire_all()
    matches_a = db.query(JobMatch).join(Job, Job.id == JobMatch.job_id).filter(
        JobMatch.user_id == user1.id
    ).all()
    matches_b = db.query(JobMatch).join(Job, Job.id == JobMatch.job_id).filter(
        JobMatch.user_id == user2.id
    ).all()
    match_a, match_b = matches_a[0], matches_b[0]
    assert {match.score for match in matches_a} == {88}
    assert {match.score for match in matches_b} == {52}
    assert match_a.analysis_status == "completed" and match_b.analysis_status == "completed"
    assert match_a.cv_checksum == "checksum-a-marker"
    assert match_b.cv_checksum == "checksum-b-marker"

    history_a = db.query(NotificationHistory).filter(
        NotificationHistory.user_id == user1.id
    ).all()
    history_b = db.query(NotificationHistory).filter(
        NotificationHistory.user_id == user2.id
    ).all()
    # The alert carried two postings, so A gets exactly two messages (and each
    # match is recorded once thanks to the dedupe key).
    assert len(history_a) == 2
    assert all(entry.status == "sent" for entry in history_a)
    assert len({entry.dedupe_key for entry in history_a}) == 2
    assert len(history_b) == 0

    sent_a = telegram_states[TOKEN_A].sent
    assert len(sent_a) == 2
    assert {message["chat_id"] for message in sent_a} == {CHAT_A}
    assert all("%88" in message["text"] for message in sent_a)
    assert telegram_states[TOKEN_B].sent == []

    # Both stages are observable in the queue.
    kinds = [job.kind for job in db.query(SyncJob).all()]
    assert kinds.count("scoring") == 2
    assert kinds.count("notify") == 1
    assert all(
        job.status in {SyncJobStatus.COMPLETED.value, SyncJobStatus.CANCELLED.value}
        for job in db.query(SyncJob).filter(SyncJob.kind.in_(["scoring", "notify"]))
    )


def test_two_user_isolation_after_the_pipeline(db, user1, user2, api_user1, api_user2, fake_providers):
    account_a = prepare_user(db, user1, "A-Marker", TOKEN_A, CHAT_A)
    account_b = prepare_user(db, user2, "B-Marker", TOKEN_B, CHAT_B)
    telegram_states = {
        TOKEN_A: FakeTelegramState(token=TOKEN_A),
        TOKEN_B: FakeTelegramState(token=TOKEN_B),
    }
    telegram_states[TOKEN_A].register_chat(CHAT_A, title="Kullanıcı A")
    telegram_states[TOKEN_B].register_chat(CHAT_B, title="Kullanıcı B")

    provider_factory = FakeClientFactory(
        {
            "gmail": FakeMailProviderClient(
                provider="gmail",
                state=FakeProviderState(
                    messages=message_map(v1_message("iso-a")),
                    pages=[gmail_page(["iso-a"], checkpoint="h1")],
                ),
            )
        }
    )
    run_scan(db, user1, account_a, provider_factory)
    provider_factory.clients["gmail"].reset_pages([gmail_page(["iso-a"], checkpoint="h2")])
    run_scan(db, user2, account_b, provider_factory)

    llm_factory, _ = routing_llm_factory()
    runner = SyncRunner(
        worker_id="e2e-iso",
        client_factory=provider_factory,
        llm_factory=llm_factory,
        telegram_factory=telegram_factory(telegram_states),
        now=WINDOW_NOW,
    )
    from app.services.scoring_service import ScoringService

    for user in (user1, user2):
        ScoringService(db).enqueue_for_new_jobs(user.id)
    db.commit()
    drain_queue(runner)

    db.expire_all()
    match_b = db.query(JobMatch).join(Job, Job.id == JobMatch.job_id).filter(
        JobMatch.user_id == user2.id
    ).first()

    # A cannot read B's analysis, notification or Telegram config.
    assert api_user1.get(f"/api/v1/jobs/{match_b.job_id}").status_code == 404
    assert api_user1.post(f"/api/v1/jobs/{match_b.job_id}/reanalyze").status_code == 404

    notifications_a = api_user1.get("/api/v1/notifications").json()
    assert all(
        item["job_title"] != "AI Engineer" or item["score"] == 88
        for item in notifications_a["items"]
    )
    status_a = api_user1.get("/api/v1/integrations/telegram/status").json()
    assert status_a["chat_id"] == CHAT_A
    assert status_a["bot_username"] == "bot_100001"
    assert TOKEN_B not in api_user1.get("/api/v1/integrations").text

    telegram_b = TelegramRepository(db).get_for_user(user2.id)
    assert telegram_b.chat_id == CHAT_B

    # A's delivered message never contains B's chat or token.
    delivered = telegram_states[TOKEN_A].sent
    assert delivered and all(CHAT_B not in message["text"] for message in delivered)
