"""Tests for Docker resilience: healthchecks, graceful shutdown, lease recovery, idempotency."""

from __future__ import annotations

import asyncio
import signal
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.enums import SyncJobAccountStatus, SyncJobStatus
from app.models.job import Job
from app.models.sync_job import ScoringItem, SyncJob, SyncJobAccount
from app.repositories.sync_jobs import SyncJobAccountRepository, SyncJobRepository
from app.services.sync_job_service import SyncRunner
from app.worker import run_worker
from app.worker_health import check_health
from tests.fakes import FakeProviderState, gmail_page
from tests.fixtures import emails
from tests.test_scan_pipeline import WINDOW_NOW, message_map, v1_message


class TestHealthEndpoints:
    def test_health_returns_ok(self):
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "app" in data
        assert "environment" in data

    def test_readiness_returns_ready_when_db_ok(self):
        client = TestClient(app)
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    def test_readiness_returns_503_when_db_unreachable(self):
        client = TestClient(app)
        with patch("app.main.engine.connect", side_effect=Exception("Database connection timeout")):
            response = client.get("/health/ready")
            assert response.status_code == 503
            assert response.json()["status"] == "not_ready"


class TestWorkerHealthCheck:
    def test_worker_health_check_passes(self, db):
        assert check_health(engine_instance=db.bind) == 0

    def test_worker_health_check_fails_on_db_error(self):
        with patch("app.worker_health.engine.connect", side_effect=Exception("DB unavailable")):
            assert check_health() == 1


class TestWorkerGracefulShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_event_stops_worker_immediately(self):
        shutdown_event = asyncio.Event()
        runner = SyncRunner(worker_id="test-shutdown")

        # Set shutdown event right away
        shutdown_event.set()

        start_time = asyncio.get_running_loop().time()
        # Even with large poll_seconds, it should return immediately because shutdown_event is set
        processed = await runner.run_forever(poll_seconds=10.0, shutdown_event=shutdown_event)
        elapsed = asyncio.get_running_loop().time() - start_time

        assert processed == 0
        assert elapsed < 1.0  # immediately unblocked

    @pytest.mark.asyncio
    async def test_shutdown_event_unblocks_idle_sleep(self):
        shutdown_event = asyncio.Event()
        runner = SyncRunner(worker_id="test-shutdown-idle")

        async def trigger_shutdown_later():
            await asyncio.sleep(0.1)
            shutdown_event.set()

        asyncio.create_task(trigger_shutdown_later())
        start_time = asyncio.get_running_loop().time()
        processed = await runner.run_forever(poll_seconds=10.0, shutdown_event=shutdown_event)
        elapsed = asyncio.get_running_loop().time() - start_time

        assert processed == 0
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_run_worker_handles_signals(self):
        shutdown_event = asyncio.Event()
        runner = SyncRunner(worker_id="test-signal")

        shutdown_event.set()
        processed = await run_worker(
            runner, poll_seconds=0.1, shutdown_event=shutdown_event
        )
        assert processed == 0


class TestCrashRecoveryAndLeaseSafety:
    def _create_running_stale_job(self, db, user, account, *, expired=True):
        now = datetime.now(timezone.utc)
        lease_expires = (
            now - timedelta(minutes=5) if expired else now + timedelta(minutes=5)
        )
        job = SyncJob(
            user_id=user.id,
            status=SyncJobStatus.RUNNING.value,
            trigger="manual",
            worker_id="crashed-worker-container",
            started_at=now - timedelta(minutes=10),
            heartbeat_at=now - timedelta(minutes=6),
            lease_expires_at=lease_expires,
            attempt=1,
            accounts_total=1,
            account_ids=[str(account.id)],
        )
        db.add(job)
        db.flush()

        job_account = SyncJobAccount(
            sync_job_id=job.id,
            user_id=user.id,
            mail_account_id=account.id,
            status=SyncJobAccountStatus.RUNNING.value,
        )
        db.add(job_account)

        posting = Job(
            user_id=user.id,
            source="gmail",
            external_id=f"test-posting-{uuid.uuid4().hex[:8]}",
            title="Software Engineer",
            company="Acme Corp",
            is_mock=False,
        )
        db.add(posting)
        db.flush()

        scoring_item = ScoringItem(
            sync_job_id=job.id,
            user_id=user.id,
            job_id=posting.id,
            status="running",
            attempt=1,
        )
        db.add(scoring_item)
        db.commit()
        return job

    def test_stale_job_recovered_on_worker_loop(self, db, user1, mailbox, fake_providers):
        account = mailbox("gmail")
        job = self._create_running_stale_job(db, user1, account, expired=True)

        factory, _ = fake_providers(
            gmail=FakeProviderState(
                messages=message_map(v1_message("recovered-msg")),
                pages=[gmail_page(["recovered-msg"], checkpoint="h-recovered")],
            )
        )

        runner = SyncRunner(
            worker_id="new-worker-after-crash",
            client_factory=factory,
            now=WINDOW_NOW,
        )

        # run_forever recovers stale job and completes it
        processed = asyncio.run(runner.run_forever(once=True))
        assert processed == 1

        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        assert refreshed.status == SyncJobStatus.COMPLETED.value
        assert refreshed.attempt == 2

        # Verify account and scoring item are no longer in running state
        account_rows = SyncJobAccountRepository(db).list_for_job(job.id)
        assert account_rows[0].status == SyncJobAccountStatus.SUCCEEDED.value

        scoring_items = (
            db.query(ScoringItem).filter(ScoringItem.sync_job_id == job.id).all()
        )
        assert scoring_items[0].status == "queued"

    def test_unexpired_lease_not_recovered_prematurely(self, db, user1, mailbox):
        account = mailbox("gmail")
        job = self._create_running_stale_job(db, user1, account, expired=False)

        recovered_count = SyncRunner(worker_id="inspector").recover()
        assert recovered_count == 0

        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        assert refreshed.status == SyncJobStatus.RUNNING.value

    def test_recovery_is_idempotent_no_duplicate_jobs(
        self, db, user1, mailbox, fake_providers
    ):
        account = mailbox("gmail")
        job = self._create_running_stale_job(db, user1, account, expired=True)

        factory, _ = fake_providers(
            gmail=FakeProviderState(
                messages=message_map(v1_message("idempotent-msg")),
                pages=[gmail_page(["idempotent-msg"], checkpoint="h-idemp")],
            )
        )

        runner = SyncRunner(
            worker_id="worker-recovery",
            client_factory=factory,
            now=WINDOW_NOW,
        )
        asyncio.run(runner.run_forever(once=True))

        # Re-running recovery on completed job does nothing
        assert runner.recover() == 0
        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        assert refreshed.status == SyncJobStatus.COMPLETED.value
