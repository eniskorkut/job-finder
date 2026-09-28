"""Tests for bounded job-level retries and durable retry delay."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.models.enums import SyncJobAccountStatus, SyncJobStatus
from app.models.job import Job
from app.models.sync_job import ScoringItem, SyncJob, SyncJobAccount
from app.repositories.sync_jobs import SyncJobAccountRepository, SyncJobRepository
from app.services.sync_job_service import SyncRunner


class TestJobRetryDelayAndBounds:
    def test_claim_does_not_take_future_retry(self, db, user1, mailbox):
        account = mailbox("gmail")
        now = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)

        job = SyncJob(
            user_id=user1.id,
            status=SyncJobStatus.QUEUED.value,
            trigger="manual",
            attempt=1,
            next_attempt_at=now + timedelta(seconds=10),
            accounts_total=1,
            account_ids=[str(account.id)],
        )
        db.add(job)
        db.commit()

        # At 'now', job next_attempt_at is 10s in the future -> cannot be claimed
        runner = SyncRunner(worker_id="test-worker", clock_now=now)
        assert runner.claim() is None

        # At 'now + 5s', still in the future -> cannot be claimed
        runner_5s = SyncRunner(worker_id="test-worker", clock_now=now + timedelta(seconds=5))
        assert runner_5s.claim() is None

        # At 'now + 10s', next_attempt_at has arrived -> claimed!
        runner_10s = SyncRunner(worker_id="test-worker", clock_now=now + timedelta(seconds=10))
        claimed_id = runner_10s.claim()
        assert claimed_id == job.id

        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        assert refreshed.status == SyncJobStatus.RUNNING.value
        assert refreshed.attempt == 2
        assert refreshed.next_attempt_at is None

    def test_claim_ignores_queued_job_exceeding_max_attempts(self, db, user1, mailbox):
        account = mailbox("gmail")
        now = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)

        job = SyncJob(
            user_id=user1.id,
            status=SyncJobStatus.QUEUED.value,
            trigger="manual",
            attempt=settings.sync_max_attempts,  # 3
            next_attempt_at=None,
            accounts_total=1,
            account_ids=[str(account.id)],
        )
        db.add(job)
        db.commit()

        runner = SyncRunner(worker_id="test-worker", now=now)
        assert runner.claim() is None

    @pytest.mark.asyncio
    async def test_unexpected_execution_exception_is_bounded(self, db, user1, mailbox):
        account = mailbox("gmail")
        clock = datetime(2026, 9, 28, 14, 0, 0, tzinfo=timezone.utc)

        job = SyncJob(
            user_id=user1.id,
            status=SyncJobStatus.QUEUED.value,
            trigger="manual",
            attempt=0,
            accounts_total=1,
            account_ids=[str(account.id)],
        )
        db.add(job)
        db.flush()

        posting = Job(
            user_id=user1.id,
            source="gmail",
            external_id="test-ext-id",
            title="Software Engineer",
            company="Test Inc",
            is_mock=False,
        )
        db.add(posting)
        db.flush()

        item = ScoringItem(
            sync_job_id=job.id,
            user_id=user1.id,
            job_id=posting.id,
            status="queued",
            attempt=0,
        )
        db.add(item)
        db.commit()

        class MutableClockRunner(SyncRunner):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.current_time = clock

            def _clock_now(self):
                return self.current_time

            async def _execute_mail_scan(self, job_id):
                # Always simulate an unhandled unexpected error during execution
                raise RuntimeError("Simulated unhandled execution failure")

        runner = MutableClockRunner(worker_id="bounded-worker")

        # --- Cycle 1: First Attempt ---
        # Worker claims job and attempts execute. execute() raises, worker catches and releases.
        processed = await runner.run_forever(once=True)
        assert processed == 0  # failed, not successfully processed

        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        assert refreshed.status == SyncJobStatus.QUEUED.value
        assert refreshed.attempt == 1
        assert refreshed.next_attempt_at is not None
        next_attempt = refreshed.next_attempt_at
        if next_attempt.tzinfo is None:
            next_attempt = next_attempt.replace(tzinfo=timezone.utc)
        assert next_attempt == runner.current_time + timedelta(seconds=5.0)

        # Immediate claim at current time MUST NOT claim it (no hot loop!)
        assert runner.claim() is None

        # --- Cycle 2: Second Attempt after backoff ---
        # Advance time by 5 seconds
        runner.current_time += timedelta(seconds=5.0)

        processed = await runner.run_forever(once=True)
        assert processed == 0

        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        assert refreshed.status == SyncJobStatus.QUEUED.value
        assert refreshed.attempt == 2
        next_attempt = refreshed.next_attempt_at
        if next_attempt.tzinfo is None:
            next_attempt = next_attempt.replace(tzinfo=timezone.utc)
        assert next_attempt == runner.current_time + timedelta(seconds=15.0)

        # Immediate claim at current time MUST NOT claim it
        assert runner.claim() is None

        # --- Cycle 3: Third Attempt after backoff ---
        # Advance time by 15 seconds
        runner.current_time += timedelta(seconds=15.0)

        processed = await runner.run_forever(once=True)
        assert processed == 0

        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        # Reached max attempts (3) -> Job marked FAILED!
        assert refreshed.status == SyncJobStatus.FAILED.value
        assert refreshed.attempt == 3
        assert refreshed.finished_at is not None
        assert refreshed.next_attempt_at is None
        assert "Beklenmeyen yürütme hatası" in (refreshed.error_message or "")

        # Even after advancing time 1000 seconds, job is never claimed again
        runner.current_time += timedelta(seconds=1000.0)
        assert runner.claim() is None
