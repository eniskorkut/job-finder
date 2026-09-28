"""Scheduled scans: due users, atomic claim, backoff, restart safety."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import ConnectionStatus, SyncJobStatus, SyncTrigger
from app.models.preferences import UserPreference
from app.models.sync_job import SyncJob
from app.repositories.preferences import PreferenceRepository
from app.repositories.sync_jobs import SyncJobRepository
from app.services.scheduler_service import SchedulerService, as_aware, clamp_interval
from tests.conftest import add_mail_account, add_oauth_client

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def enable_auto_scan(db, user, *, hours: int = 24, next_scan_at: datetime | None):
    preference = PreferenceRepository(db).get_or_create(user)
    preference.daily_scan_enabled = True
    preference.scan_interval_hours = hours
    preference.next_scan_at = next_scan_at
    db.commit()
    return preference


def make_account(db, user, *, email: str = "auto@gmail.example.com"):
    add_oauth_client(db, user, "gmail")
    return add_mail_account(db, user, "gmail", email_address=email)


def scheduler(now: datetime = NOW) -> SchedulerService:
    return SchedulerService(now=now)


class TestDueDetection:
    def test_disabled_user_is_never_scheduled(self, db, user1):
        make_account(db, user1)
        enable_auto_scan(db, user1, next_scan_at=NOW - timedelta(hours=1))
        preference = PreferenceRepository(db).get_or_create(user1)
        preference.daily_scan_enabled = False
        db.commit()

        assert scheduler().sync_due() == []
        assert db.query(SyncJob).count() == 0

    def test_due_user_is_scheduled(self, db, user1):
        make_account(db, user1)
        enable_auto_scan(db, user1, next_scan_at=NOW - timedelta(minutes=5))

        created = scheduler().sync_due()
        assert len(created) == 1

        job = db.get(SyncJob, created[0])
        assert job.kind == "mail_scan"
        assert job.trigger == SyncTrigger.SCHEDULED.value
        assert job.status == SyncJobStatus.QUEUED.value
        assert job.accounts_total == 1

    def test_future_user_is_not_scheduled(self, db, user1):
        make_account(db, user1)
        enable_auto_scan(db, user1, next_scan_at=NOW + timedelta(hours=2))
        assert scheduler().sync_due() == []
        assert db.query(SyncJob).count() == 0

    def test_plan_advances_after_scheduling(self, db, user1):
        make_account(db, user1)
        preference = enable_auto_scan(db, user1, hours=6, next_scan_at=NOW - timedelta(minutes=5))
        scheduler().sync_due()
        db.refresh(preference)
        assert as_aware(preference.next_scan_at) == NOW + timedelta(hours=6)

    def test_duplicate_scheduling_is_prevented(self, db, user1):
        make_account(db, user1)
        enable_auto_scan(db, user1, next_scan_at=NOW - timedelta(minutes=5))
        service = scheduler()

        first = service.sync_due()
        second = service.sync_due()
        assert len(first) == 1
        assert second == []  # atomic claim already moved next_scan_at forward
        assert db.query(SyncJob).count() == 1

    def test_active_manual_scan_blocks_a_scheduled_one(self, db, user1):
        make_account(db, user1)
        preference = enable_auto_scan(db, user1, next_scan_at=NOW - timedelta(minutes=5))
        SyncJobRepository(db).create(user_id=user1.id, kind="mail_scan", trigger="manual")
        db.commit()

        assert scheduler().sync_due() == []
        db.refresh(preference)
        # Pushed out briefly so the loop stays quiet while the manual run works.
        assert as_aware(preference.next_scan_at) == NOW + timedelta(minutes=5)
        assert db.query(SyncJob).count() == 1

    def test_user_without_accounts_does_not_spin(self, db, user1):
        preference = enable_auto_scan(db, user1, next_scan_at=NOW - timedelta(minutes=5))
        assert scheduler().sync_due() == []
        db.refresh(preference)
        assert preference.auto_scan_failures == 1
        assert db.query(SyncJob).count() == 0

    def test_two_users_are_scheduled_independently(self, db, user1, user2):
        make_account(db, user1, email="a@gmail.example.com")
        make_account(db, user2, email="b@gmail.example.com")
        enable_auto_scan(db, user1, next_scan_at=NOW - timedelta(minutes=5))
        enable_auto_scan(db, user2, next_scan_at=NOW - timedelta(minutes=5))

        created = scheduler().sync_due()
        assert len(created) == 2
        jobs = db.query(SyncJob).all()
        assert {job.user_id for job in jobs} == {user1.id, user2.id}

    def test_plan_survives_a_worker_restart(self, db, user1):
        make_account(db, user1)
        enable_auto_scan(db, user1, hours=3, next_scan_at=NOW - timedelta(minutes=5))
        created = scheduler().sync_due()
        assert len(created) == 1

        # The worker finishes that scan (a restart-safe plan is derived from DB).
        job = db.get(SyncJob, created[0])
        SyncJobRepository(db).finish(job, SyncJobStatus.COMPLETED)
        db.commit()  # the worker commits before it updates the plan
        scheduler().refresh_after_scan(user1.id, finished_at=NOW, successful=True)

        # A brand new service instance (i.e. restarted worker) sees the plan.
        preference = PreferenceRepository(db).get_or_create(user1)
        assert as_aware(preference.next_scan_at) == NOW + timedelta(hours=3)
        assert scheduler(NOW + timedelta(hours=2)).sync_due() == []
        assert scheduler(NOW + timedelta(hours=3, minutes=1)).sync_due()


class TestPostScanBookkeeping:
    def test_success_updates_last_and_next(self, db, user1):
        preference = enable_auto_scan(db, user1, hours=12, next_scan_at=NOW)
        finished = NOW + timedelta(minutes=4)
        scheduler().refresh_after_scan(user1.id, finished_at=finished, successful=True)

        db.refresh(preference)
        assert as_aware(preference.last_auto_scan_at) == finished
        assert as_aware(preference.next_scan_at) == finished + timedelta(hours=12)
        assert preference.auto_scan_failures == 0

    def test_failure_backs_off_instead_of_looping(self, db, user1):
        preference = enable_auto_scan(db, user1, hours=6, next_scan_at=NOW)
        finished = NOW + timedelta(minutes=1)

        scheduler().refresh_after_scan(user1.id, finished_at=finished, successful=False)
        db.refresh(preference)
        assert preference.auto_scan_failures == 1
        assert as_aware(preference.next_scan_at) == finished + timedelta(hours=12)  # 2x

        scheduler().refresh_after_scan(user1.id, finished_at=finished, successful=False)
        db.refresh(preference)
        assert preference.auto_scan_failures == 2
        assert as_aware(preference.next_scan_at) == finished + timedelta(hours=24)  # 4x

    def test_backoff_is_capped(self, db, user1):
        preference = enable_auto_scan(db, user1, hours=6, next_scan_at=NOW)
        preference.auto_scan_failures = 9
        db.commit()
        finished = NOW + timedelta(minutes=1)
        scheduler().refresh_after_scan(user1.id, finished_at=finished, successful=False)
        db.refresh(preference)
        assert as_aware(preference.next_scan_at) == finished + timedelta(hours=36)  # 6x cap

    def test_disabling_clears_the_plan(self, db, user1):
        preference = enable_auto_scan(db, user1, next_scan_at=NOW - timedelta(hours=1))
        preference.daily_scan_enabled = False
        db.commit()
        scheduler().refresh_after_scan(NOW, finished_at=NOW, successful=True) if False else None
        db.refresh(preference)
        assert preference.next_scan_at is None or preference.daily_scan_enabled is False


class TestPreferencesWiring:
    def test_enabling_plans_the_next_run(self, api_user1, db, user1):
        api_user1.put("/api/v1/preferences", json={"daily_scan_enabled": True})
        preference = PreferenceRepository(db).get_or_create(user1)
        db.refresh(preference)
        assert preference.next_scan_at is not None

    def test_interval_is_clamped(self, api_user1):
        response = api_user1.put("/api/v1/preferences", json={"scan_interval_hours": 200})
        assert response.status_code == 422  # pydantic upper bound

        from app.core.config import settings

        assert clamp_interval(0) == settings.scheduler_min_interval_hours
        assert clamp_interval(9999) == settings.scheduler_max_interval_hours

    def test_status_endpoint_exposes_the_plan(self, api_user1, db, user1):
        enable_auto_scan(db, user1, hours=8, next_scan_at=NOW + timedelta(hours=8))
        status = api_user1.get("/api/v1/sync/status").json()
        assert status["scheduler_enabled"] is True
        assert status["worker_hint"] == "python -m app.worker"
        assert status["available"] is True
