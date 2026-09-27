"""Scan pipeline: parsing into per-user jobs, dedupe, cursors, resilience."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.integrations.errors import CursorExpiredError, ProviderAuthError, ProviderError
from app.models.enums import (
    ConnectionStatus,
    CursorKind,
    ErrorClass,
    ProcessedMessageStatus,
    SyncJobAccountStatus,
    SyncJobStatus,
)
from app.models.job import Job
from app.models.mail_account import MailAccount
from app.models.sync_job import JobSource, ProcessedMessage, SyncCheckpoint
from app.repositories.jobs import MailAccountRepository
from app.repositories.sync_jobs import CheckpointRepository, ProcessedMessageRepository
from tests.conftest import add_mail_account, run_scan
from tests.fakes import (
    FakeClientFactory,
    FakeMailProviderClient,
    FakeProviderState,
    gmail_page,
    graph_page,
)
from tests.fixtures import emails

WINDOW_NOW = emails.RECEIVED_AT + timedelta(days=1)


def gmail_state(*, messages: dict, pages, **kwargs) -> FakeProviderState:
    return FakeProviderState(messages=messages, pages=pages, **kwargs)


def message_map(*messages) -> dict:
    return {message.external_id: message for message in messages}


def v1_message(external_id: str = "msg-1") -> "emails.RawMessage":
    return emails.raw_message(
        external_id=external_id,
        subject="NovaTech AI için yeni iş ilanı",
        html=emails.HTML_TABLE_V1,
    )


class TestInitialScan:
    def test_ingests_jobs_with_sources_checkpoint_and_counters(
        self, db, user1, mailbox, fake_providers
    ):
        account = mailbox("gmail")
        factory, clients = fake_providers(
            gmail=gmail_state(
                messages=message_map(v1_message()),
                pages=[gmail_page(["msg-1"], checkpoint="history-100")],
            )
        )

        job, outcome = run_scan(db, user1, account, factory)

        assert outcome.status == SyncJobAccountStatus.SUCCEEDED
        assert outcome.messages_scanned == 1
        assert (outcome.jobs_found, outcome.jobs_new, outcome.jobs_duplicate) == (2, 2, 0)

        jobs = db.query(Job).filter(Job.user_id == user1.id).order_by(Job.title).all()
        assert [job.title for job in jobs] == ["LLM Engineer", "Senior AI Engineer"]
        senior = next(job for job in jobs if job.title == "Senior AI Engineer")
        assert senior.source == "gmail"
        assert senior.is_mock is False
        assert senior.external_id == "4012345678"
        assert "trk=" not in (senior.url or "")
        assert senior.url == senior.url_normalized
        assert senior.description_status == "ok"

        sources = db.query(JobSource).filter(JobSource.job_id == senior.id).all()
        assert len(sources) == 1
        assert sources[0].provider == "gmail"
        assert sources[0].provider_message_id == "msg-1"
        assert sources[0].mail_account_id == account.id
        assert sources[0].sender == "jobalerts-noreply@linkedin.com"

        processed = db.query(ProcessedMessage).filter(ProcessedMessage.user_id == user1.id).all()
        assert len(processed) == 1
        assert processed[0].status == ProcessedMessageStatus.PROCESSED.value
        assert processed[0].jobs_found == 2

        checkpoint = CheckpointRepository(db).get_for_account(account.id)
        assert checkpoint.cursor_kind == CursorKind.GMAIL_HISTORY.value
        assert checkpoint.cursor_value == "history-100"
        assert checkpoint.initial_sync_completed is True

        db.refresh(account)
        assert account.initial_sync_completed is True
        assert account.last_synced_at is not None

        db.refresh(job)
        assert job.messages_scanned == 1
        assert job.jobs_new == 2
        assert job.accounts_processed == 1

    def test_scan_is_idempotent_for_the_same_message(self, db, user1, mailbox, fake_providers):
        account = mailbox("gmail")
        factory, clients = fake_providers(
            gmail=gmail_state(
                messages=message_map(v1_message()),
                pages=[gmail_page(["msg-1"], checkpoint="h1")],
            )
        )
        run_scan(db, user1, account, factory)
        assert db.query(Job).filter(Job.user_id == user1.id).count() == 2

        # Same page again (e.g. the worker restarted before moving the cursor).
        clients["gmail"].reset_pages([gmail_page(["msg-1"], checkpoint="h2")])
        _, second = run_scan(db, user1, account, factory)

        assert second.jobs_new == 0
        assert second.messages_skipped == 1
        assert db.query(Job).filter(Job.user_id == user1.id).count() == 2
        assert db.query(JobSource).count() == 2

    def test_same_posting_from_two_accounts_is_one_job_with_two_sources(
        self, db, user1, mailbox, fake_providers
    ):
        gmail_account = mailbox("gmail", email_address="bir@gmail.example.com")
        outlook_account = mailbox("outlook", email_address="iki@outlook.example.com")
        message = v1_message("gmail-msg")

        gmail_factory, _ = fake_providers(
            gmail=gmail_state(
                messages=message_map(message), pages=[gmail_page(["gmail-msg"], checkpoint="h1")]
            )
        )
        run_scan(db, user1, gmail_account, gmail_factory)

        outlook_message = emails.raw_message(
            external_id="outlook-msg",
            subject="NovaTech AI için yeni iş ilanı",
            html=emails.HTML_TABLE_V1,
        )
        outlook_factory = FakeClientFactory(
            {
                "outlook": FakeMailProviderClient(
                    provider="outlook",
                    state=FakeProviderState(
                        messages=message_map(outlook_message),
                        pages=[graph_page([outlook_message], checkpoint="delta-1")],
                    ),
                )
            }
        )
        _, second = run_scan(db, user1, outlook_account, outlook_factory)

        assert second.jobs_new == 0
        assert second.jobs_duplicate == 2
        jobs = db.query(Job).filter(Job.user_id == user1.id).all()
        assert len(jobs) == 2
        for job in jobs:
            sources = db.query(JobSource).filter(JobSource.job_id == job.id).all()
            assert {source.provider for source in sources} == {"gmail", "outlook"}

    def test_messages_outside_the_first_window_are_skipped(
        self, db, user1, mailbox, fake_providers
    ):
        account = mailbox("gmail")
        old = emails.raw_message(
            external_id="old-msg",
            subject="iş ilanı",
            html=emails.HTML_DIV_V2,
            received_at=emails.RECEIVED_AT - timedelta(days=30),
        )
        factory, _ = fake_providers(
            gmail=gmail_state(
                messages=message_map(old), pages=[gmail_page(["old-msg"], checkpoint="h1")]
            )
        )
        _, outcome = run_scan(db, user1, account, factory)

        assert outcome.jobs_found == 0
        assert outcome.messages_skipped == 1
        record = db.query(ProcessedMessage).filter_by(provider_message_id="old-msg").one()
        assert record.status == ProcessedMessageStatus.SKIPPED.value
        assert record.reason == "outside_window"
        assert db.query(Job).count() == 0

    def test_custom_sender_and_subject_filters_are_applied(
        self, db, user1, mailbox, fake_providers
    ):
        account = mailbox(
            "gmail",
            filters={"senders": ["baska@firma.com"], "subjects": ["pozisyon"]},
        )
        message = v1_message("filtered-msg")
        factory, _ = fake_providers(
            gmail=gmail_state(
                messages=message_map(message),
                pages=[gmail_page(["filtered-msg"], checkpoint="h1")],
            )
        )
        _, outcome = run_scan(db, user1, account, factory)

        assert outcome.jobs_found == 0
        record = db.query(ProcessedMessage).filter_by(provider_message_id="filtered-msg").one()
        assert record.reason == "sender_filtered"

    def test_alert_without_jobs_is_recorded_as_zero(self, db, user1, mailbox, fake_providers):
        account = mailbox("gmail")
        message = emails.raw_message(
            external_id="empty-msg", subject="iş ilanı", html=emails.HTML_NO_JOBS
        )
        factory, _ = fake_providers(
            gmail=gmail_state(
                messages=message_map(message), pages=[gmail_page(["empty-msg"], checkpoint="h1")]
            )
        )
        _, outcome = run_scan(db, user1, account, factory)

        assert outcome.status == SyncJobAccountStatus.SUCCEEDED
        assert outcome.jobs_found == 0
        record = db.query(ProcessedMessage).filter_by(provider_message_id="empty-msg").one()
        assert record.reason == "no_jobs"
        assert record.status == ProcessedMessageStatus.SKIPPED.value

    def test_insufficient_description_is_flagged(self, db, user1, mailbox, fake_providers):
        account = mailbox("gmail")
        message = emails.raw_message(
            external_id="thin-msg", subject="iş ilanı", html=emails.HTML_COMBINED_V3
        )
        factory, _ = fake_providers(
            gmail=gmail_state(
                messages=message_map(message), pages=[gmail_page(["thin-msg"], checkpoint="h1")]
            )
        )
        run_scan(db, user1, account, factory)
        job = db.query(Job).filter(Job.user_id == user1.id).one()
        assert job.description_status == "insufficient_description"
        assert job.description is None


class TestIncrementalScan:
    def test_second_run_uses_the_stored_history_cursor(self, db, user1, mailbox, fake_providers):
        account = mailbox("gmail")
        factory, clients = fake_providers(
            gmail=gmail_state(
                messages=message_map(v1_message()), pages=[gmail_page(["msg-1"], checkpoint="h1")]
            )
        )
        run_scan(db, user1, account, factory)

        clients["gmail"].reset_pages([gmail_page([], checkpoint="h2")])
        _, outcome = run_scan(db, user1, account, factory)

        requests = clients["gmail"].state.page_requests[1:]
        assert [request["mode"].value for request in requests] == ["incremental"]
        assert requests[0]["cursor"] == "h1"
        assert requests[0]["query"].since is None  # incremental scans are not windowed
        checkpoint = CheckpointRepository(db).get_for_account(account.id)
        assert checkpoint.cursor_value == "h2"

    def test_expired_cursor_triggers_a_bounded_resync(self, db, user1, mailbox, fake_providers):
        account = mailbox("gmail")
        factory, clients = fake_providers(
            gmail=gmail_state(
                messages=message_map(v1_message()), pages=[gmail_page(["msg-1"], checkpoint="h1")]
            )
        )
        run_scan(db, user1, account, factory)

        state = clients["gmail"].state
        # First call of the *next* run raises, the retry succeeds.
        clients["gmail"].reset_pages(
            [gmail_page([], checkpoint="unused"), gmail_page([], checkpoint="h2")]
        )
        state.fail_on_page = 0
        state.fail_error = CursorExpiredError("geçmiş penceresi kapandı", provider="gmail")

        _, outcome = run_scan(db, user1, account, factory)

        assert outcome.status == SyncJobAccountStatus.SUCCEEDED
        requests = state.page_requests[1:]
        assert [request["mode"].value for request in requests] == ["incremental", "initial"]
        checkpoint = CheckpointRepository(db).get_for_account(account.id)
        assert checkpoint.cursor_value == "h2"


class TestResilience:
    def test_message_fetch_failure_does_not_abort_the_run(
        self, db, user1, mailbox, fake_providers
    ):
        account = mailbox("gmail")
        state = gmail_state(
            messages={},  # no message bodies available
            pages=[gmail_page(["msg-1"], checkpoint="h1")],
            fetch_error=ProviderError(
                "ağ hatası", provider="gmail", error_class=ErrorClass.TRANSIENT
            ),
        )
        factory, clients = fake_providers(gmail=state)

        _, outcome = run_scan(db, user1, account, factory)

        assert outcome.status == SyncJobAccountStatus.SUCCEEDED
        assert outcome.messages_scanned == 0
        # Not marked as processed, so the next run retries it.
        assert db.query(ProcessedMessage).count() == 0
        assert CheckpointRepository(db).get_for_account(account.id).cursor_value == "h1"

    def test_auth_error_marks_the_mailbox_for_reauth(self, db, user1, mailbox, fake_providers):
        account = mailbox("gmail")
        state = FakeProviderState(
            fail_on_page=0, fail_error=ProviderAuthError("token süresi doldu", provider="gmail")
        )
        factory, _ = fake_providers(gmail=state)

        _, outcome = run_scan(db, user1, account, factory)

        assert outcome.status == SyncJobAccountStatus.FAILED
        assert outcome.error_class == ErrorClass.AUTH
        db.refresh(account)
        assert account.status == ConnectionStatus.NEEDS_REAUTH.value
        assert "token" in (account.last_error or "").lower()

    def test_transient_error_is_recorded_on_the_checkpoint(self, db, user1, mailbox, fake_providers):
        account = mailbox("gmail")
        state = FakeProviderState(
            fail_on_page=0,
            fail_error=ProviderError("geçici", provider="gmail", error_class=ErrorClass.RATE_LIMIT),
        )
        factory, _ = fake_providers(gmail=state)

        _, outcome = run_scan(db, user1, account, factory)

        assert outcome.status == SyncJobAccountStatus.FAILED
        assert outcome.error_class == ErrorClass.RATE_LIMIT
        checkpoint = CheckpointRepository(db).get_for_account(account.id)
        assert checkpoint.consecutive_failures == 1

    def test_token_refresh_happens_when_the_access_token_expired(
        self, db, user1, mailbox, fake_providers
    ):
        account = mailbox("gmail")
        account.access_token_encrypted = None  # forces a refresh
        account.token_expires_at = None
        db.commit()

        factory, clients = fake_providers(
            gmail=gmail_state(messages={}, pages=[gmail_page([], checkpoint="h1")])
        )
        run_scan(db, user1, account, factory)

        assert clients["gmail"].state.refresh_requests
        assert clients["gmail"].state.refresh_requests[0]["refresh_token"] == "refresh-token-1"
        db.refresh(account)
        assert account.access_token_encrypted is not None


class TestMultiAccountRuns:
    def test_one_failing_mailbox_does_not_block_the_other(
        self, db, user1, mailbox, fake_providers, monkeypatch
    ):
        from app.services.sync_job_service import SyncRunner

        good = mailbox("gmail", email_address="iyi@gmail.example.com")
        bad = mailbox("outlook", email_address="kotu@outlook.example.com")

        good_factory, _ = fake_providers(
            gmail=gmail_state(
                messages=message_map(v1_message("good-msg")),
                pages=[gmail_page(["good-msg"], checkpoint="h1")],
            ),
            outlook=FakeProviderState(
                fail_on_page=0,
                fail_error=ProviderAuthError("yeniden bağlan", provider="outlook"),
            ),
        )

        from app.models.enums import SyncTrigger
        from app.models.sync_job import SyncJob
        from app.repositories.sync_jobs import SyncJobAccountRepository

        job = SyncJob(
            user_id=user1.id,
            status=SyncJobStatus.QUEUED.value,
            trigger=SyncTrigger.MANUAL.value,
            accounts_total=2,
        )
        db.add(job)
        db.flush()
        SyncJobAccountRepository(db).ensure_accounts(job, [good.id, bad.id])
        db.commit()

        runner = SyncRunner(
            worker_id="test-worker",
            client_factory=good_factory,
            now=WINDOW_NOW,
        )
        assert runner.claim() == job.id
        import asyncio

        status = asyncio.run(runner.execute(job.id))

        assert status == SyncJobStatus.PARTIAL_FAILED
        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        assert refreshed.status == SyncJobStatus.PARTIAL_FAILED
        assert refreshed.accounts_processed == 2
        assert refreshed.errors_count == 1
        assert db.query(Job).filter(Job.user_id == user1.id).count() == 2
        db.refresh(good)
        db.refresh(bad)
        assert good.last_synced_at is not None
        assert bad.status == ConnectionStatus.NEEDS_REAUTH.value

    def test_users_never_share_jobs_even_with_identical_mail(
        self, db, user1, user2, mailbox, fake_providers
    ):
        first = mailbox("gmail", email_address="u1@gmail.example.com", user=user1)
        second = mailbox("gmail", email_address="u2@gmail.example.com", user=user2)

        factory_one, _ = fake_providers(
            gmail=gmail_state(
                messages=message_map(v1_message("m1")), pages=[gmail_page(["m1"], checkpoint="h1")]
            )
        )
        run_scan(db, user1, first, factory_one)

        factory_two, _ = fake_providers(
            gmail=gmail_state(
                messages=message_map(v1_message("m2")), pages=[gmail_page(["m2"], checkpoint="h1")]
            )
        )
        run_scan(db, user2, second, factory_two)

        assert db.query(Job).filter(Job.user_id == user1.id).count() == 2
        assert db.query(Job).filter(Job.user_id == user2.id).count() == 2
        assert db.query(Job).count() == 4

        user1_jobs = db.query(Job).filter(Job.user_id == user1.id).all()
        for job in user1_jobs:
            assert all(
                source.user_id == user1.id
                for source in db.query(JobSource).filter(JobSource.job_id == job.id)
            )
