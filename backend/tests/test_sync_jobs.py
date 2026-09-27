"""Durable scan jobs: enqueue (202), progress, cancel, worker, leases, isolation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import (
    ConnectionStatus,
    SyncJobAccountStatus,
    SyncJobStatus,
    SyncTrigger,
)
from app.models.job import Job
from app.models.sync_job import JobSource, SyncJob, SyncJobAccount
from app.repositories.sync_jobs import SyncJobAccountRepository, SyncJobRepository
from app.services.sync_job_service import SyncRunner
from tests.conftest import run_scan
from tests.fakes import FakeProviderState, gmail_page
from tests.fixtures import emails
from tests.test_scan_pipeline import WINDOW_NOW, message_map, v1_message


class TestEnqueue:
    def test_run_returns_202_with_a_job_id(self, api_user1, db, user1, mailbox):
        mailbox("gmail")
        response = api_user1.post("/api/v1/sync/run")
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == SyncJobStatus.QUEUED.value
        assert body["accounts_total"] == 1
        assert "python -m app.worker" in body["message"]

        job = db.get(SyncJob, uuid.UUID(body["job_id"]))
        assert job is not None
        assert job.user_id == user1.id
        assert job.trigger == SyncTrigger.MANUAL.value
        rows = SyncJobAccountRepository(db).list_for_job(job.id)
        assert len(rows) == 1

    def test_double_click_is_rejected_with_the_active_job(self, api_user1, mailbox):
        mailbox("gmail")
        first = api_user1.post("/api/v1/sync/run")
        assert first.status_code == 202
        second = api_user1.post("/api/v1/sync/run")
        assert second.status_code == 409
        assert str(first.json()["job_id"]) in second.json()["detail"]["message"]

    def test_specific_accounts_can_be_selected(self, api_user1, db, user1, mailbox):
        first = mailbox("gmail", email_address="bir@gmail.example.com")
        mailbox("outlook", email_address="iki@outlook.example.com")

        response = api_user1.post("/api/v1/sync/run", json={"account_ids": [str(first.id)]})
        assert response.status_code == 202
        assert response.json()["accounts_total"] == 1

    def test_disconnected_accounts_are_not_scanned(self, api_user1, db, mailbox):
        account = mailbox("gmail")
        account.status = ConnectionStatus.DISCONNECTED.value
        db.commit()
        response = api_user1.post("/api/v1/sync/run")
        assert response.status_code == 422
        assert "Bağlı bir e-posta hesabı yok" in response.json()["detail"]["message"]

    def test_cancel_queued_job_then_enqueue_again(self, api_user1, mailbox):
        mailbox("gmail")
        job_id = api_user1.post("/api/v1/sync/run").json()["job_id"]

        cancelled = api_user1.post(f"/api/v1/sync/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["job"]["status"] == SyncJobStatus.CANCELLED.value
        assert cancelled.json()["job"]["cancel_requested"] is True

        assert api_user1.post("/api/v1/sync/run").status_code == 202

    def test_progress_shape(self, api_user1, mailbox):
        mailbox("gmail", email_address="takip@gmail.example.com")
        job_id = api_user1.post("/api/v1/sync/run").json()["job_id"]

        response = api_user1.get(f"/api/v1/sync/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["job"]["id"] == job_id
        assert body["accounts"][0]["email_address"] == "takip@gmail.example.com"
        assert body["accounts"][0]["provider"] == "gmail"
        assert body["accounts"][0]["status"] == SyncJobAccountStatus.QUEUED.value
        for field in (
            "messages_scanned",
            "jobs_found",
            "jobs_new",
            "jobs_duplicate",
            "messages_skipped",
            "errors_count",
        ):
            assert field in body["job"]

    def test_jobs_are_owner_scoped(self, api_user1, api_user2, mailbox):
        mailbox("gmail")
        job_id = api_user1.post("/api/v1/sync/run").json()["job_id"]

        assert api_user2.get(f"/api/v1/sync/jobs/{job_id}").status_code == 404
        assert api_user2.post(f"/api/v1/sync/jobs/{job_id}/cancel").status_code == 404
        assert api_user2.get("/api/v1/sync/jobs").json()["total"] == 0

    def test_history_and_status_endpoints_stay_compatible(self, api_user1):
        history = api_user1.get("/api/v1/sync/history")
        assert history.status_code == 200
        assert history.json()["total"] == 0

        status = api_user1.get("/api/v1/sync/status").json()
        assert status["available"] is True
        assert status["running"] is False
        assert status["worker_hint"] == "python -m app.worker"


class TestWorker:
    def test_worker_once_processes_the_queued_job(
        self, api_user1, db, user1, mailbox, fake_providers
    ):
        account = mailbox("gmail")
        job_id = api_user1.post("/api/v1/sync/run").json()["job_id"]

        factory, _ = fake_providers(
            gmail=FakeProviderState(
                messages=message_map(v1_message("worker-msg")),
                pages=[gmail_page(["worker-msg"], checkpoint="h1")],
            )
        )
        runner = SyncRunner(worker_id="worker-test", client_factory=factory, now=WINDOW_NOW)
        processed = asyncio.run(runner.run_forever(once=True))

        assert processed == 1
        db.expire_all()
        job = db.get(SyncJob, uuid.UUID(job_id))
        assert job.status == SyncJobStatus.COMPLETED.value
        assert job.accounts_processed == 1
        assert job.jobs_new == 2
        assert job.started_at is not None
        assert job.finished_at is not None
        assert db.query(Job).filter(Job.user_id == user1.id).count() == 2

        progress = api_user1.get(f"/api/v1/sync/jobs/{job_id}").json()
        assert progress["accounts"][0]["status"] == SyncJobAccountStatus.SUCCEEDED.value
        assert progress["accounts"][0]["jobs_new"] == 2

    def test_worker_reports_partial_failure(
        self, api_user1, db, user1, mailbox, fake_providers
    ):
        mailbox("gmail", email_address="iyi@gmail.example.com")
        mailbox("outlook", email_address="kotu@outlook.example.com")
        job_id = api_user1.post("/api/v1/sync/run").json()["job_id"]

        from app.integrations.errors import ProviderAuthError

        factory, _ = fake_providers(
            gmail=FakeProviderState(
                messages=message_map(v1_message("ok-msg")),
                pages=[gmail_page(["ok-msg"], checkpoint="h1")],
            ),
            outlook=FakeProviderState(
                fail_on_page=0,
                fail_error=ProviderAuthError("yeniden bağlan", provider="outlook"),
            ),
        )
        runner = SyncRunner(worker_id="worker-test", client_factory=factory, now=WINDOW_NOW)
        asyncio.run(runner.run_forever(once=True))

        db.expire_all()
        job = db.get(SyncJob, uuid.UUID(job_id))
        assert job.status == SyncJobStatus.PARTIAL_FAILED.value
        assert job.errors_count == 1
        assert job.accounts_processed == 2
        statuses = {row.status for row in SyncJobAccountRepository(db).list_for_job(job.id)}
        assert statuses == {
            SyncJobAccountStatus.SUCCEEDED.value,
            SyncJobAccountStatus.FAILED.value,
        }

        progress = api_user1.get(f"/api/v1/sync/jobs/{job_id}").json()
        assert any(account["error_message"] for account in progress["accounts"])

    def test_cancel_during_a_run_stops_the_mailboxes(
        self, api_user1, db, user1, mailbox, fake_providers
    ):
        mailbox("gmail")
        job_id = api_user1.post("/api/v1/sync/run").json()["job_id"]
        # Cancel before the worker picks it up: the run is skipped, not failed.
        api_user1.post(f"/api/v1/sync/jobs/{job_id}/cancel")

        factory, _ = fake_providers(
            gmail=FakeProviderState(
                messages=message_map(v1_message("x")),
                pages=[gmail_page(["x"], checkpoint="h1")],
            )
        )
        runner = SyncRunner(worker_id="worker-test", client_factory=factory, now=WINDOW_NOW)
        asyncio.run(runner.run_forever(once=True))

        db.expire_all()
        job = db.get(SyncJob, uuid.UUID(job_id))
        assert job.status == SyncJobStatus.CANCELLED.value
        assert db.query(Job).count() == 0

    def test_missing_worker_leaves_the_job_queued(self, api_user1, db, mailbox):
        mailbox("gmail")
        job_id = api_user1.post("/api/v1/sync/run").json()["job_id"]
        # No worker runs: the job stays queued and the UI can explain that.
        db.expire_all()
        assert db.get(SyncJob, uuid.UUID(job_id)).status == SyncJobStatus.QUEUED.value
        status = api_user1.get("/api/v1/sync/status").json()
        assert status["running"] is True
        assert status["active_job_id"] == job_id


class TestLeaseRecovery:
    def _stale_job(self, db, user, account, *, attempt: int) -> SyncJob:
        job = SyncJob(
            user_id=user.id,
            status=SyncJobStatus.RUNNING.value,
            trigger=SyncTrigger.MANUAL.value,
            accounts_total=1,
            attempt=attempt,
            worker_id="crashed-worker",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db.add(job)
        db.flush()
        SyncJobAccountRepository(db).ensure_accounts(job, [account.id])
        rows = SyncJobAccountRepository(db).list_for_job(job.id)
        SyncJobAccountRepository(db).mark_running(rows[0])
        db.commit()
        return job

    def test_expired_lease_is_requeued(self, db, user1, mailbox):
        account = mailbox("gmail")
        job = self._stale_job(db, user1, account, attempt=1)

        runner = SyncRunner(worker_id="recovery-test")
        assert runner.recover() == 1

        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        assert refreshed.status == SyncJobStatus.QUEUED.value
        assert refreshed.worker_id is None
        assert refreshed.lease_expires_at is None
        rows = SyncJobAccountRepository(db).list_for_job(job.id)
        assert rows[0].status == SyncJobAccountStatus.QUEUED.value

    def test_expired_lease_without_attempts_left_fails(self, db, user1, mailbox):
        account = mailbox("gmail")
        job = self._stale_job(db, user1, account, attempt=3)

        SyncRunner(worker_id="recovery-test").recover()

        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        assert refreshed.status == SyncJobStatus.FAILED.value
        assert refreshed.error_message
        assert refreshed.finished_at is not None

    def test_recovered_job_can_be_processed_again(
        self, db, user1, mailbox, fake_providers
    ):
        account = mailbox("gmail")
        job = self._stale_job(db, user1, account, attempt=1)

        factory, _ = fake_providers(
            gmail=FakeProviderState(
                messages=message_map(v1_message("again")),
                pages=[gmail_page(["again"], checkpoint="h1")],
            )
        )
        runner = SyncRunner(worker_id="recovery-test", client_factory=factory, now=WINDOW_NOW)
        asyncio.run(runner.run_forever(once=True))

        db.expire_all()
        refreshed = db.get(SyncJob, job.id)
        assert refreshed.status == SyncJobStatus.COMPLETED.value
        assert refreshed.attempt == 2
        assert db.query(Job).filter(Job.user_id == user1.id).count() == 2

    def test_claim_returns_nothing_when_the_queue_is_empty(self):
        assert SyncRunner(worker_id="idle").claim() is None


class TestUserIsolationOnSync:
    def test_second_user_run_does_not_touch_the_first_users_data(
        self, db, user1, user2, mailbox, fake_providers
    ):
        first_account = mailbox("gmail", email_address="u1@gmail.example.com", user=user1)
        second_account = mailbox("gmail", email_address="u2@gmail.example.com", user=user2)

        first_factory, _ = fake_providers(
            gmail=FakeProviderState(
                messages=message_map(v1_message("u1-msg")),
                pages=[gmail_page(["u1-msg"], checkpoint="h1")],
            )
        )
        run_scan(db, user1, first_account, first_factory)

        second_factory, _ = fake_providers(
            gmail=FakeProviderState(
                messages=message_map(v1_message("u2-msg")),
                pages=[gmail_page(["u2-msg"], checkpoint="h1")],
            )
        )
        run_scan(db, user2, second_account, second_factory)

        assert db.query(Job).filter(Job.user_id == user1.id).count() == 2
        assert db.query(Job).filter(Job.user_id == user2.id).count() == 2
        # Sources belong to the owner of the job.
        assert all(
            source.user_id == user2.id
            for source in db.query(JobSource).filter(
                JobSource.provider_message_id == "u2-msg"
            )
        )
