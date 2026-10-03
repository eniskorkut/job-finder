from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models.job import Job, JobMatch, JobWebSource
from app.models.mail_account import MailAccount
from app.repositories.base import Repository

SORT_OPTIONS = {
    "recent": (Job.discovered_at.desc(), Job.id.desc()),
    "oldest": (Job.discovered_at.asc(), Job.id.asc()),
    "score": (JobMatch.score.desc().nulls_last(), Job.discovered_at.desc()),
    "confidence": (JobMatch.confidence.desc().nulls_last(), Job.discovered_at.desc()),
    "score_asc": (JobMatch.score.asc().nulls_last(), Job.discovered_at.desc()),
    "company": (Job.company.asc(), Job.discovered_at.desc()),
    "title": (Job.title.asc(), Job.discovered_at.desc()),
    "posted_at": (Job.posted_at.desc().nulls_last(), Job.discovered_at.desc()),
    "freshness": (Job.freshness_status.asc(), Job.discovered_at.desc()),
    "verified": (Job.last_verified_at.desc().nulls_last(), Job.discovered_at.desc()),
}


class JobRepository(Repository[Job]):
    model = Job

    def _base_query(self, user_id: uuid.UUID):
        return select(Job).where(Job.user_id == user_id)

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        search: str | None = None,
        company: str | None = None,
        location: str | None = None,
        work_mode: str | None = None,
        source: str | None = None,
        status: str | None = None,
        min_score: int | None = None,
        max_score: int | None = None,
        analysis_status: str | None = None,
        notification: str | None = None,
        freshness_status: str | None = None,
        enrichment_status: str | None = None,
        sort: str = "recent",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Job], int]:
        def apply_filters(stmt):
            if search:
                pattern = f"%{search.strip().lower()}%"
                stmt = stmt.where(
                    or_(
                        func.lower(Job.title).like(pattern),
                        func.lower(Job.company).like(pattern),
                        func.lower(func.coalesce(Job.location, "")).like(pattern),
                        func.lower(func.coalesce(Job.description, "")).like(pattern),
                    )
                )
            if company:
                stmt = stmt.where(func.lower(Job.company) == company.strip().lower())
            if location:
                pattern = f"%{location.strip().lower()}%"
                stmt = stmt.where(func.lower(func.coalesce(Job.location, "")).like(pattern))
            if work_mode:
                stmt = stmt.where(Job.work_mode == work_mode)
            if source:
                if source == "official_ats":
                    stmt = stmt.where(
                        or_(
                            Job.canonical_url.is_not(None),
                            Job.company_job_url.is_not(None),
                            Job.source == "official_ats",
                        )
                    )
                elif source == "linkedin":
                    stmt = stmt.where(Job.linkedin_url.is_not(None))
                elif source == "mail":
                    stmt = stmt.where(Job.source.in_(["gmail", "outlook"]))
                else:
                    stmt = stmt.where(Job.source == source)
            if freshness_status:
                stmt = stmt.where(Job.freshness_status == freshness_status)
            if enrichment_status:
                stmt = stmt.where(Job.enrichment_status == enrichment_status)
            return stmt

        count_stmt = apply_filters(
            select(func.count(func.distinct(Job.id)))
            .select_from(Job)
            .outerjoin(JobMatch, JobMatch.job_id == Job.id)
            .where(Job.user_id == user_id)
        )
        if status:
            count_stmt = count_stmt.where(JobMatch.status == status)
        if min_score is not None:
            count_stmt = count_stmt.where(JobMatch.score >= min_score)
        if max_score is not None:
            count_stmt = count_stmt.where(JobMatch.score <= max_score)
        total = int(self.db.execute(count_stmt).scalar_one())

        stmt = apply_filters(
            self._base_query(user_id)
            .options(selectinload(Job.match), selectinload(Job.web_sources))
            .outerjoin(JobMatch, JobMatch.job_id == Job.id)
        )
        if status:
            stmt = stmt.where(JobMatch.status == status)
        if min_score is not None:
            stmt = stmt.where(JobMatch.score >= min_score)
        if max_score is not None:
            stmt = stmt.where(JobMatch.score <= max_score)

        order_by = SORT_OPTIONS.get(sort, SORT_OPTIONS["recent"])
        stmt = stmt.order_by(*order_by).offset(offset).limit(limit)
        jobs = list(self.db.execute(stmt).unique().scalars())
        return jobs, total

    def get_for_user(self, user_id: uuid.UUID, job_id: uuid.UUID) -> Job | None:
        stmt = (
            select(Job)
            .options(selectinload(Job.match), selectinload(Job.web_sources))
            .where(Job.id == job_id, Job.user_id == user_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_match_for_user(self, user_id: uuid.UUID, job_id: uuid.UUID) -> JobMatch | None:
        stmt = select(JobMatch).where(
            JobMatch.job_id == job_id, JobMatch.user_id == user_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def stats(self, user_id: uuid.UUID, high_match_threshold: int = 70) -> dict:
        total = int(
            self.db.execute(
                select(func.count(Job.id)).where(Job.user_id == user_id)
            ).scalar_one()
        )
        new_jobs = int(
            self.db.execute(
                select(func.count(Job.id))
                .select_from(Job)
                .outerjoin(JobMatch, JobMatch.job_id == Job.id)
                .where(Job.user_id == user_id, JobMatch.status == "new")
            ).scalar_one()
        )
        high_match = int(
            self.db.execute(
                select(func.count(Job.id))
                .select_from(Job)
                .outerjoin(JobMatch, JobMatch.job_id == Job.id)
                .where(Job.user_id == user_id, JobMatch.score >= high_match_threshold)
            ).scalar_one()
        )
        saved = int(
            self.db.execute(
                select(func.count(JobMatch.id)).where(
                    JobMatch.user_id == user_id, JobMatch.status == "saved"
                )
            ).scalar_one()
        )
        dismissed = int(
            self.db.execute(
                select(func.count(JobMatch.id)).where(
                    JobMatch.user_id == user_id, JobMatch.status == "dismissed"
                )
            ).scalar_one()
        )
        mock_jobs = int(
            self.db.execute(
                select(func.count(Job.id)).where(Job.user_id == user_id, Job.is_mock.is_(True))
            ).scalar_one()
        )
        average_score = self.db.execute(
            select(func.avg(JobMatch.score)).where(
                JobMatch.user_id == user_id, JobMatch.score.is_not(None)
            )
        ).scalar_one()
        average_confidence = self.db.execute(
            select(func.avg(JobMatch.confidence)).where(
                JobMatch.user_id == user_id, JobMatch.confidence.is_not(None)
            )
        ).scalar_one()
        real_jobs = int(
            self.db.execute(
                select(func.count(Job.id)).where(
                    Job.user_id == user_id, Job.is_mock.is_(False)
                )
            ).scalar_one()
        )
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        discovered_today = int(
            self.db.execute(
                select(func.count(Job.id)).where(
                    Job.user_id == user_id,
                    Job.is_mock.is_(False),
                    Job.discovered_at >= today_start,
                )
            ).scalar_one()
        )
        analysis_rows = self.db.execute(
            select(JobMatch.analysis_status, func.count(JobMatch.id))
            .join(Job, Job.id == JobMatch.job_id)
            .where(JobMatch.user_id == user_id, Job.is_mock.is_(False))
            .group_by(JobMatch.analysis_status)
        ).all()
        analysis_counts = {status or "pending": int(count) for status, count in analysis_rows}
        analyzed_jobs = analysis_counts.get("completed", 0)
        failed_analysis = analysis_counts.get("failed", 0)
        notified_jobs = int(
            self.db.execute(
                select(func.count(JobMatch.id))
                .join(Job, Job.id == JobMatch.job_id)
                .where(JobMatch.user_id == user_id, JobMatch.notified_at.is_not(None))
            ).scalar_one()
        )

        source_rows = self.db.execute(
            select(Job.source, func.count(Job.id))
            .where(Job.user_id == user_id)
            .group_by(Job.source)
        ).all()
        company_rows = self.db.execute(
            select(Job.company, func.count(Job.id))
            .where(Job.user_id == user_id)
            .group_by(Job.company)
            .order_by(func.count(Job.id).desc())
            .limit(5)
        ).all()

        enrich_rows = self.db.execute(
            select(Job.enrichment_status, func.count(Job.id))
            .where(Job.user_id == user_id, Job.is_mock.is_(False))
            .group_by(Job.enrichment_status)
        ).all()
        enrich_counts = {status: int(count) for status, count in enrich_rows}
        enriched_jobs = enrich_counts.get("enriched", 0)
        pending_enrichment = enrich_counts.get("pending", 0)
        problematic_enrichment = (
            enrich_counts.get("failed", 0)
            + enrich_counts.get("search_unavailable", 0)
            + enrich_counts.get("fetch_failed", 0)
        )

        fresh_rows = self.db.execute(
            select(Job.freshness_status, func.count(Job.id))
            .where(Job.user_id == user_id, Job.is_mock.is_(False))
            .group_by(Job.freshness_status)
        ).all()
        fresh_counts = {status: int(count) for status, count in fresh_rows}
        fresh_jobs = fresh_counts.get("fresh", 0)
        aging_jobs = fresh_counts.get("aging", 0)
        stale_jobs = fresh_counts.get("stale", 0)
        expired_jobs = fresh_counts.get("expired", 0)

        return {
            "total_jobs": total,
            "new_jobs": new_jobs,
            "high_match_jobs": high_match,
            "saved_jobs": saved,
            "dismissed_jobs": dismissed,
            "mock_jobs": mock_jobs,
            "high_match_threshold": high_match_threshold,
            "average_score": round(float(average_score), 1) if average_score is not None else None,
            "jobs_by_source": {row[0]: int(row[1]) for row in source_rows},
            "top_companies": [{"company": row[0], "count": int(row[1])} for row in company_rows],
            "real_jobs": real_jobs,
            "discovered_today": discovered_today,
            "analyzed_jobs": analyzed_jobs,
            "pending_analysis": max(0, real_jobs - analyzed_jobs - failed_analysis),
            "failed_analysis": failed_analysis,
            "notified_jobs": notified_jobs,
            "average_confidence": (
                round(float(average_confidence), 1)
                if average_confidence is not None
                else None
            ),
            "enriched_jobs": enriched_jobs,
            "pending_enrichment": pending_enrichment,
            "problematic_enrichment": problematic_enrichment,
            "fresh_jobs": fresh_jobs,
            "aging_jobs": aging_jobs,
            "stale_jobs": stale_jobs,
            "expired_jobs": expired_jobs,
        }

    def filter_options(self, user_id: uuid.UUID) -> dict:
        sources = self.db.execute(
            select(Job.source).where(Job.user_id == user_id).group_by(Job.source)
        ).scalars()
        locations = self.db.execute(
            select(Job.location)
            .where(Job.user_id == user_id, Job.location.is_not(None))
            .group_by(Job.location)
            .order_by(Job.location)
        ).scalars()
        companies = self.db.execute(
            select(Job.company).where(Job.user_id == user_id).group_by(Job.company).order_by(Job.company)
        ).scalars()
        work_modes = self.db.execute(
            select(Job.work_mode).where(Job.user_id == user_id).group_by(Job.work_mode)
        ).scalars()
        analysis_statuses = self.db.execute(
            select(JobMatch.analysis_status)
            .join(Job, Job.id == JobMatch.job_id)
            .where(JobMatch.user_id == user_id)
            .group_by(JobMatch.analysis_status)
        ).scalars()
        freshness_statuses = self.db.execute(
            select(Job.freshness_status)
            .where(Job.user_id == user_id, Job.freshness_status.is_not(None))
            .group_by(Job.freshness_status)
        ).scalars()
        enrichment_statuses = self.db.execute(
            select(Job.enrichment_status)
            .where(Job.user_id == user_id, Job.enrichment_status.is_not(None))
            .group_by(Job.enrichment_status)
        ).scalars()
        return {
            "sources": list(sources),
            "locations": list(locations),
            "companies": list(companies),
            "work_modes": list(work_modes),
            "analysis_statuses": [status for status in analysis_statuses if status],
            "freshness_statuses": [status for status in freshness_statuses if status],
            "enrichment_statuses": [status for status in enrichment_statuses if status],
        }

    def latest_discovered_at(self, user_id: uuid.UUID) -> datetime | None:
        return self.db.execute(
            select(func.max(Job.discovered_at)).where(Job.user_id == user_id)
        ).scalar_one()

    def touch_match_view(self, match: JobMatch) -> None:
        if match.status == "new":
            match.status = "viewed"
            self.db.flush()


class MailAccountRepository(Repository[MailAccount]):
    model = MailAccount

    def list_for_user(self, user_id: uuid.UUID) -> list[MailAccount]:
        stmt = (
            select(MailAccount)
            .where(MailAccount.user_id == user_id)
            .order_by(MailAccount.created_at)
        )
        return list(self.db.execute(stmt).scalars())

    def get_for_user(self, user_id: uuid.UUID, account_id: uuid.UUID) -> MailAccount | None:
        stmt = select(MailAccount).where(
            MailAccount.id == account_id, MailAccount.user_id == user_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_provider(
        self, user_id: uuid.UUID, provider: str, account_id: uuid.UUID
    ) -> MailAccount | None:
        account = self.get_for_user(user_id, account_id)
        if account is None or account.provider != provider:
            return None
        return account

    def get_by_address(
        self, user_id: uuid.UUID, provider: str, email_address: str
    ) -> MailAccount | None:
        stmt = select(MailAccount).where(
            MailAccount.user_id == user_id,
            MailAccount.provider == provider,
            func.lower(MailAccount.email_address) == email_address.strip().lower(),
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_connected(self, user_id: uuid.UUID) -> list[MailAccount]:
        stmt = (
            select(MailAccount)
            .where(
                MailAccount.user_id == user_id,
                MailAccount.status != ConnectionStatus.DISCONNECTED.value,
            )
            .order_by(MailAccount.created_at)
        )
        return list(self.db.execute(stmt).scalars())

    def connected_count(self, user_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count(MailAccount.id)).where(
                    MailAccount.user_id == user_id, MailAccount.status == "connected"
                )
            ).scalar_one()
        )

    def latest_sync_at(self, user_id: uuid.UUID) -> datetime | None:
        return self.db.execute(
            select(func.max(MailAccount.last_synced_at)).where(MailAccount.user_id == user_id)
        ).scalar_one()

    def mark_disconnected(self, account: MailAccount) -> None:
        account.status = "disconnected"
        account.access_token_encrypted = None
        account.refresh_token_encrypted = None
        account.token_expires_at = None
        account.last_error = None
        self.db.flush()


class JobWebSourceRepository(Repository[JobWebSource]):
    model = JobWebSource

    def list_for_job(self, job_id: uuid.UUID) -> list[JobWebSource]:
        stmt = (
            select(JobWebSource)
            .where(JobWebSource.job_id == job_id)
            .order_by(JobWebSource.trust_level.desc(), JobWebSource.discovered_at.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def get_by_normalized_url(
        self, job_id: uuid.UUID, normalized_url: str
    ) -> JobWebSource | None:
        stmt = select(JobWebSource).where(
            JobWebSource.job_id == job_id,
            JobWebSource.normalized_url == normalized_url,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert(
        self,
        *,
        user_id: uuid.UUID,
        job_id: uuid.UUID,
        url: str,
        normalized_url: str,
        host: str,
        source_type: str,
        trust_level: int = 0,
        match_confidence: str = "none",
        title: str | None = None,
        snippet: str | None = None,
        http_status: int | None = None,
        content_hash: str | None = None,
        selected_as_canonical: bool = False,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> JobWebSource:
        existing = self.get_by_normalized_url(job_id, normalized_url)
        if existing is not None:
            existing.url = url
            existing.host = host
            existing.source_type = source_type
            existing.trust_level = max(existing.trust_level, trust_level)
            existing.match_confidence = match_confidence or existing.match_confidence
            if title:
                existing.title = title
            if snippet:
                existing.snippet = snippet
            if http_status is not None:
                existing.http_status = http_status
            if content_hash:
                existing.content_hash = content_hash
            if etag:
                existing.etag = etag
            if last_modified:
                existing.last_modified = last_modified
            if selected_as_canonical:
                existing.selected_as_canonical = True
            existing.last_checked_at = datetime.now(timezone.utc)
            self.db.flush()
            return existing

        source = JobWebSource(
            user_id=user_id,
            job_id=job_id,
            url=url,
            normalized_url=normalized_url,
            host=host,
            source_type=source_type,
            trust_level=trust_level,
            match_confidence=match_confidence,
            title=title,
            snippet=snippet,
            http_status=http_status,
            content_hash=content_hash,
            etag=etag,
            last_modified=last_modified,
            selected_as_canonical=selected_as_canonical,
            discovered_at=datetime.now(timezone.utc),
            last_checked_at=datetime.now(timezone.utc),
        )
        self.db.add(source)
        self.db.flush()
        return source
