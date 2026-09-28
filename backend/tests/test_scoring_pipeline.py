"""Durable scoring pipeline: profiles, idempotency, isolation, failure handling."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest

from app.core.crypto import encrypt_secret
from app.integrations.errors import ProviderError
from app.models.enums import ErrorClass, SyncJobStatus, SyncTrigger
from app.models.job import Job, JobMatch
from app.models.llm import CVProfile, LlmUsage
from app.models.sync_job import ScoringItem, SyncJob
from app.repositories.jobs import JobRepository
from app.repositories.sync_jobs import SyncJobRepository
from app.services.profile_service import CVProfileService
from app.services.scoring_runner import ScoringRunner
from app.services.scoring_service import (
    ANALYSIS_COMPLETED,
    ANALYSIS_FAILED,
    MODE_NEW,
    MODE_REANALYZE,
    ScoringService,
)
from tests.conftest import add_mail_account, add_oauth_client
from tests.fakes_phase3 import FakeLlmState, fake_llm_factory
from tests.test_scan_pipeline import WINDOW_NOW, message_map, v1_message
from tests.fakes import FakeProviderState, gmail_page
from tests.conftest import run_scan


def make_real_jobs(db, user, count: int = 2, *, titles: list[str] | None = None) -> list[Job]:
    """Insert real (non mock) jobs with pending matches, as ingest would."""
    jobs: list[Job] = []
    for index in range(count):
        title = (titles or [])[index] if titles and index < len(titles) else f"AI Engineer {index + 1}"
        job = Job(
            user_id=user.id,
            source="gmail",
            external_id=f"linkedin-{uuid.uuid4().hex[:12]}",
            title=title,
            company=f"Şirket {index + 1}",
            location="İstanbul, Türkiye",
            work_mode="hybrid",
            description="Python, FastAPI ve RAG deneyimi bekliyoruz. " * 5,
            description_status="ok",
            is_mock=False,
        )
        db.add(job)
        db.flush()
        db.add(
            JobMatch(
                user_id=user.id,
                job_id=job.id,
                score=None,
                matched_skills=[],
                missing_skills=[],
                analysis_status="pending",
                is_mock=False,
            )
        )
        jobs.append(job)
    db.commit()
    return jobs


def add_cv(db, user, *, text: str | None = None, checksum: str = "checksum-a") -> None:
    from app.models.cv import CV

    # Mirror CVService.upload: only one CV is active at a time.
    db.query(CV).filter(CV.user_id == user.id).update({CV.is_active: False})
    cv = CV(
        user_id=user.id,
        filename="cv.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_path=f"{user.id}/cv.pdf",
        checksum=checksum,
        extracted_text=text
        or (
            "Enis Korkut - AI Engineer\n"
            "6 yıl deneyim: Python, FastAPI, PyTorch, RAG, vektör veritabanları.\n"
            "Telefon: +90 (532) 111 22 33\nE-posta: enis@example.com\n"
        ),
        extraction_status="ok",
        is_active=True,
    )
    db.add(cv)
    db.commit()
    return cv


def run_scoring(db, job_id: uuid.UUID, state: FakeLlmState, *, now=None) -> object:
    """Run a scoring job the way the worker does, including job bookkeeping."""
    from app.db.session import SessionLocal
    from app.models.sync_job import SyncJob as _SyncJob
    from app.repositories.sync_jobs import SyncJobRepository as _Queue

    runner = ScoringRunner(
        llm_factory=fake_llm_factory(state),
        session_factory=SessionLocal,
        now=now,
    )
    outcome = asyncio.run(runner.run(job_id))
    with SessionLocal() as session:
        job = session.get(_SyncJob, job_id)
        if job is not None:
            _Queue(session).finish(job, outcome.status, error=outcome.error_message)
        session.commit()
    db.expire_all()
    return outcome


class TestProfileCache:
    def test_profile_is_extracted_once_and_reused(self, db, user1):
        add_cv(db, user1)
        make_real_jobs(db, user1, 2)
        state = FakeLlmState(score_by_title={"AI Engineer 1": 90, "AI Engineer 2": 70})
        service = ScoringService(db)
        job, total = service.enqueue(user1, mode=MODE_NEW)
        db.commit()
        assert total == 2

        run_scoring(db, job.id, state)
        assert state.profile_calls == 1
        assert len(state.score_calls) == 2

        db.expire_all()
        profile = db.query(CVProfile).filter(CVProfile.user_id == user1.id).one()
        assert profile.status == "ready"
        assert profile.cv_checksum == "checksum-a"
        assert profile.profile["skills"]
        assert profile.prompt_version

        # Second run for the other job reuses the cached profile.
        make_real_jobs(db, user1, 1, titles=["ML Engineer"])
        job2, total2 = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        assert total2 == 1
        run_scoring(db, job2.id, state)
        assert state.profile_calls == 1  # still one extraction

    def test_new_cv_invalidates_the_profile(self, db, user1):
        add_cv(db, user1)
        make_real_jobs(db, user1, 1)
        state = FakeLlmState()
        job, _ = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        run_scoring(db, job.id, state)
        assert state.profile_calls == 1

        # New active CV -> checksum changes -> stale profile -> re-extraction.
        add_cv(db, user1, text="Yeni CV: Kubernetes ve Go deneyimi. " * 5, checksum="checksum-b")
        db.expire_all()
        assert CVProfileService(db).cached_profile(user1) is None

        make_real_jobs(db, user1, 1, titles=["Platform Engineer"])
        job2, _ = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        run_scoring(db, job2.id, state)
        assert state.profile_calls == 2
        db.expire_all()
        assert db.query(CVProfile).filter(CVProfile.user_id == user1.id).one().cv_checksum == "checksum-b"

    def test_profile_failure_fails_the_job_without_touching_jobs(self, db, user1):
        add_cv(db, user1)
        jobs = make_real_jobs(db, user1, 1)
        state = FakeLlmState(
            profile_error=ProviderError(
                "LLM erişilemedi", provider="deepseek", error_class=ErrorClass.TRANSIENT
            )
        )
        job, _ = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        outcome = run_scoring(db, job.id, state)

        assert outcome.status == SyncJobStatus.FAILED
        db.expire_all()
        assert db.query(Job).filter(Job.id == jobs[0].id).count() == 1
        assert db.query(JobMatch).one().analysis_status == "pending"  # retryable later
        assert db.query(LlmUsage).filter(LlmUsage.purpose == "profile").one().status == "failed"


class TestScoring:
    def test_match_fields_are_written(self, db, user1):
        add_cv(db, user1)
        jobs = make_real_jobs(db, user1, 1, titles=["AI Engineer 1"])
        state = FakeLlmState(score_by_title={"AI Engineer 1": 88}, confidence=77)
        job, _ = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        outcome = run_scoring(db, job.id, state)

        assert outcome.status == SyncJobStatus.COMPLETED
        db.expire_all()
        match = db.query(JobMatch).filter(JobMatch.job_id == jobs[0].id).one()
        assert match.score == 88
        assert match.confidence == 77
        assert match.analysis_status == ANALYSIS_COMPLETED
        assert match.analyzed_at is not None
        assert match.cv_checksum == "checksum-a"
        assert match.prompt_version
        assert match.model == "fake-llm"
        assert match.experience_match == "match"
        assert match.location_match == "partial"
        assert match.match_details["experience"]["reason"]
        assert match.rationale

        item = db.query(ScoringItem).one()
        assert item.status == "succeeded"
        assert item.match_id == match.id

    def test_one_failing_job_does_not_stop_the_others(self, db, user1):
        add_cv(db, user1)
        jobs = make_real_jobs(db, user1, 3, titles=["AI Engineer 1", "AI Engineer 2", "AI Engineer 3"])
        state = FakeLlmState(
            score_by_title={"AI Engineer 2": 60},
            score_errors_by_title={
                "AI Engineer 2": ProviderError(
                    "model patladı", provider="deepseek", error_class=ErrorClass.TRANSIENT
                )
            },
        )
        job, _ = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        outcome = run_scoring(db, job.id, state)

        assert outcome.status == SyncJobStatus.PARTIAL_FAILED
        assert outcome.analyzed == 2
        assert outcome.failed == 1
        db.expire_all()
        statuses = {
            match.analysis_status
            for match in db.query(JobMatch).filter(JobMatch.user_id == user1.id)
        }
        assert statuses == {ANALYSIS_COMPLETED, ANALYSIS_FAILED}
        failed = (
            db.query(JobMatch)
            .join(Job, Job.id == JobMatch.job_id)
            .filter(Job.title == "AI Engineer 2")
            .one()
        )
        assert "model patladı" in (failed.analysis_error or "")
        assert failed.analysis_attempts == 1
        # Retryable: the failed one stays eligible for a later reanalysis.
        eligible = ScoringService(db).eligible_jobs(user1, mode=MODE_NEW)
        assert [job.title for job in eligible] == ["AI Engineer 2"]

    def test_analysis_is_not_repeated_for_the_same_cv(self, db, user1):
        add_cv(db, user1)
        make_real_jobs(db, user1, 1)
        state = FakeLlmState()
        job, _ = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        run_scoring(db, job.id, state)
        assert len(state.score_calls) == 1

        # Nothing pending with the same CV checksum.
        from app.core import errors

        with pytest.raises(errors.AppError) as exc:
            ScoringService(db).enqueue(user1, mode=MODE_REANALYZE)
        assert exc.value.detail["code"] == "conflict"
        assert len(state.score_calls) == 1

    def test_second_enqueue_is_rejected_while_running(self, db, user1):
        add_cv(db, user1)
        make_real_jobs(db, user1, 1)
        ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        from app.core import errors

        with pytest.raises(errors.AppError) as exc:
            ScoringService(db).enqueue(user1, mode=MODE_NEW)
        assert exc.value.detail["code"] == "conflict"

    def test_scoring_requires_an_active_cv_with_text(self, db, user1):
        make_real_jobs(db, user1, 1)
        from app.core import errors

        with pytest.raises(errors.AppError) as exc:
            ScoringService(db).enqueue(user1, mode=MODE_NEW)
        assert "aktif CV" in exc.value.detail["message"]

    def test_mock_jobs_are_never_analyzed(self, db, user1):
        add_cv(db, user1)
        # Phase 1 sample data must never be sent to the shared LLM.
        job = Job(
            user_id=user1.id,
            source="mock",
            external_id="mock-sample-1",
            title="Senior AI Engineer",
            company="NovaTech AI",
            is_mock=True,
        )
        db.add(job)
        db.flush()
        db.add(JobMatch(user_id=user1.id, job_id=job.id, score=92, is_mock=True))
        db.commit()

        from app.core import errors

        with pytest.raises(errors.AppError):
            ScoringService(db).enqueue(user1, mode=MODE_REANALYZE, force=True)
        assert db.query(JobMatch).filter(JobMatch.is_mock.is_(True)).one().score == 92

    def test_usage_metrics_are_recorded_per_user(self, db, user1, user2):
        add_cv(db, user1)
        make_real_jobs(db, user1, 1)
        state = FakeLlmState()
        job, _ = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        run_scoring(db, job.id, state)

        db.expire_all()
        rows = db.query(LlmUsage).all()
        assert {row.user_id for row in rows} == {user1.id}
        assert {row.purpose for row in rows} == {"profile", "scoring"}
        assert all(row.total_tokens == 200 for row in rows)
        assert db.query(LlmUsage).filter(LlmUsage.user_id == user2.id).count() == 0

    def test_scoring_items_are_claimed_once(self, db, user1):
        add_cv(db, user1)
        jobs = make_real_jobs(db, user1, 1)
        job, _ = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        item = db.query(ScoringItem).one()

        from app.repositories.sync_jobs import ScoringItemRepository

        repo = ScoringItemRepository(db)
        assert repo.claim(item) is True
        db.commit()
        # A second worker cannot claim the same (job, cv) unit.
        assert repo.claim(item) is False


class TestPipelineIntegration:
    def test_mail_scan_queues_scoring_and_scoring_feeds_matches(
        self, db, user1, mailbox, fake_providers
    ):
        """The worker chains mail_scan -> scoring through the same queue."""
        from app.services.sync_job_service import SyncRunner

        add_cv(db, user1)
        account = mailbox("gmail")
        from app.services.sync_job_service import SyncJobService

        SyncJobService(db).enqueue(user1)
        db.commit()
        factory, _ = fake_providers(
            gmail=FakeProviderState(
                messages=message_map(v1_message("pipeline-msg")),
                pages=[gmail_page(["pipeline-msg"], checkpoint="h1")],
            )
        )
        llm_state = FakeLlmState(default_score=91)
        runner = SyncRunner(
            worker_id="pipeline-test",
            client_factory=factory,
            llm_factory=fake_llm_factory(llm_state),
            now=WINDOW_NOW,
        )

        # One worker cycle: mail scan finishes and enqueues scoring.
        assert asyncio.run(runner.run_forever(once=True)) == 1

        db.expire_all()
        scoring_jobs = db.query(SyncJob).filter(SyncJob.kind == "scoring").all()
        assert len(scoring_jobs) == 1
        assert scoring_jobs[0].status == SyncJobStatus.QUEUED.value
        queued_job_id = scoring_jobs[0].id

        # Second cycle: the scoring job runs and fills the match rows.
        assert asyncio.run(runner.run_forever(once=True)) == 1
        db.expire_all()
        scoring_job = db.get(SyncJob, queued_job_id)
        assert scoring_job.status == SyncJobStatus.COMPLETED.value
        assert scoring_job.progress["analyzed"] == 2

        matches = (
            db.query(JobMatch)
            .join(Job, Job.id == JobMatch.job_id)
            .filter(JobMatch.user_id == user1.id, Job.is_mock.is_(False))
            .all()
        )
        assert len(matches) == 2
        assert {match.score for match in matches} == {91}
        assert all(match.analysis_status == ANALYSIS_COMPLETED for match in matches)


class TestIsolation:
    def test_scoring_is_scoped_to_the_owner(self, db, user1, user2, mailbox):
        add_cv(db, user1, checksum="u1-cv")
        add_cv(db, user2, checksum="u2-cv")
        jobs_a = make_real_jobs(db, user1, 1, titles=["A Engineer"])
        jobs_b = make_real_jobs(db, user2, 1, titles=["B Engineer"])

        state = FakeLlmState()
        service = ScoringService(db)
        job_a, _ = service.enqueue(user1, mode=MODE_NEW)
        db.commit()
        run_scoring(db, job_a.id, state)

        db.expire_all()
        match_a = db.query(JobMatch).filter(JobMatch.job_id == jobs_a[0].id).one()
        match_b = db.query(JobMatch).filter(JobMatch.job_id == jobs_b[0].id).one()
        assert match_a.analysis_status == ANALYSIS_COMPLETED
        assert match_b.analysis_status == "pending"
        # The prompt only ever contained the owner's profile.
        assert all(
            call["candidate_profile"].get("skills") for call in state.score_calls
        )

    def test_api_cannot_read_another_users_scoring_job(self, api_user1, api_user2, db, user1):
        job = SyncJobRepository(db).create(
            user_id=user1.id, kind="scoring", trigger=SyncTrigger.MANUAL.value
        )
        db.commit()
        assert api_user2.get(f"/api/v1/sync/jobs/{job.id}").status_code == 404
        assert api_user2.post(f"/api/v1/jobs/{uuid.uuid4()}/reanalyze").status_code == 404

    def test_reanalyze_endpoint_is_durable_and_bounded(self, api_user1, db, user1):
        add_cv(db, user1)
        make_real_jobs(db, user1, 2)
        response = api_user1.post("/api/v1/jobs/reanalyze", json={"days": 30})
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["total"] == 2
        assert db.get(SyncJob, uuid.UUID(body["job_id"])).kind == "scoring"

    def test_reanalyze_with_unchanged_cv_does_no_work(self, api_user1, db, user1):
        add_cv(db, user1)
        make_real_jobs(db, user1, 1)
        state = FakeLlmState()
        job, _ = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        run_scoring(db, job.id, state)

        response = api_user1.post("/api/v1/jobs/reanalyze", json={"days": 30})
        assert response.status_code == 409
        assert "değerlendirilmemiş ilan yok" in response.json()["detail"]["message"]

    def test_single_job_reanalyze_forces_a_fresh_analysis(self, api_user1, db, user1):
        add_cv(db, user1)
        jobs = make_real_jobs(db, user1, 1)
        state = FakeLlmState(default_score=70)
        job, _ = ScoringService(db).enqueue(user1, mode=MODE_NEW)
        db.commit()
        run_scoring(db, job.id, state)

        response = api_user1.post(f"/api/v1/jobs/{jobs[0].id}/reanalyze")
        assert response.status_code == 202
        assert response.json()["total"] == 1

        # The new analysis overwrites the score (history is not deleted).
        run_scoring(db, uuid.UUID(response.json()["job_id"]), FakeLlmState(default_score=95))
        db.expire_all()
        assert db.query(JobMatch).one().score == 95
