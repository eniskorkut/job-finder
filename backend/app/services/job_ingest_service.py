"""Turn a parsed alert e-mail into per-user job records.

Rules enforced here (all scoped to one owner):

* dedupe priority: LinkedIn job id -> normalized URL -> fingerprint,
* every message that mentioned the posting is kept as a ``JobSource``,
* a posting is never merged across users,
* alerts without enough text are marked ``insufficient_description`` instead
  of inventing content.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.base import JobPostingCandidate, RawMessage
from app.integrations.parsing.dedupe import fingerprint_hash, normalize_url
from app.models.enums import DescriptionStatus, JobSource as JobSourceKind
from app.models.enums import WorkMode
from app.models.job import Job, JobMatch
from app.models.mail_account import MailAccount
from app.repositories.sync_jobs import JobSourceRepository


@dataclass(slots=True)
class IngestResult:
    jobs_found: int = 0
    jobs_new: int = 0
    jobs_duplicate: int = 0
    job_ids: list[uuid.UUID] = field(default_factory=list)


class JobIngestService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.sources = JobSourceRepository(db)

    def ingest_message(
        self,
        *,
        user_id: uuid.UUID,
        account: MailAccount,
        message: RawMessage,
        candidates: list[JobPostingCandidate],
    ) -> IngestResult:
        result = IngestResult(jobs_found=0)
        for candidate in candidates:
            job, is_new = self._upsert(
                user_id=user_id, account=account, candidate=candidate
            )
            if job is None:
                continue
            result.jobs_found += 1
            if is_new:
                result.jobs_new += 1
            else:
                result.jobs_duplicate += 1
            if job.id not in result.job_ids:
                result.job_ids.append(job.id)
            if not self.sources.exists(job.id, message.external_id):
                self.sources.add(
                    user_id=user_id,
                    job_id=job.id,
                    mail_account_id=account.id,
                    provider=account.provider,
                    provider_message_id=message.external_id,
                    subject=message.subject,
                    sender=message.sender,
                    received_at=message.received_at,
                )
        self.db.flush()
        return result

    # ------------------------------------------------------------------
    def _upsert(
        self,
        *,
        user_id: uuid.UUID,
        account: MailAccount,
        candidate: JobPostingCandidate,
    ) -> tuple[Job | None, bool]:
        title = " ".join((candidate.title or "").split())[:300]
        company = " ".join((candidate.company or "").split())[:200] or "Bilinmiyor"
        if not title:
            return None, False

        normalized = normalize_url(candidate.url)
        fingerprint = fingerprint_hash(
            title=title,
            company=company,
            location=candidate.location,
            job_id=candidate.external_id,
        )

        existing = self._find_existing(
            user_id=user_id,
            external_id=candidate.external_id,
            url_normalized=normalized,
            fingerprint=fingerprint,
        )

        is_new = existing is None
        if existing is None:
            job = Job(
                user_id=user_id,
                mail_account_id=account.id,
                source=account.provider,
                external_id=candidate.external_id,
                title=title,
                company=company,
                location=(candidate.location or None),
                work_mode=_guess_work_mode(candidate.location, candidate.description),
                description=candidate.description,
                # Only the cleaned URL is stored; tracking parameters are gone.
                url=normalized,
                url_normalized=normalized,
                fingerprint_hash=fingerprint,
                description_status=candidate.description_status,
                posted_at=None,
                discovered_at=datetime.now(timezone.utc),
                is_mock=False,
                raw_payload={
                    "provider": account.provider,
                    "account_email": account.email_address,
                    "source_kind": JobSourceKind.__name__,
                },
            )
            self.db.add(job)
            self.db.flush()
            self.db.add(
                JobMatch(
                    user_id=user_id,
                    job_id=job.id,
                    score=None,
                    matched_skills=[],
                    missing_skills=[],
                    status="new",
                    is_mock=False,
                )
            )
            self.db.flush()
            return job, True

        # Duplicate: enrich only, never overwrite richer content with poorer.
        self._enrich(existing, candidate)
        existing.mail_account_id = existing.mail_account_id or account.id
        return existing, False

    def _find_existing(
        self,
        *,
        user_id: uuid.UUID,
        external_id: str | None,
        url_normalized: str | None,
        fingerprint: str,
    ) -> Job | None:
        if external_id:
            found = self.db.execute(
                select(Job).where(
                    Job.user_id == user_id, Job.external_id == external_id
                )
            ).scalars().first()
            if found is not None:
                return found
        if url_normalized:
            found = self.db.execute(
                select(Job).where(
                    Job.user_id == user_id, Job.url_normalized == url_normalized
                )
            ).scalars().first()
            if found is not None:
                return found
        return self.db.execute(
            select(Job).where(
                Job.user_id == user_id, Job.fingerprint_hash == fingerprint
            )
        ).scalars().first()

    def _enrich(self, job: Job, candidate: JobPostingCandidate) -> None:
        if len(candidate.description or "") > len(job.description or ""):
            job.description = candidate.description
            job.description_status = candidate.description_status
        if not job.url:
            job.url = normalize_url(candidate.url)
        if not job.url_normalized:
            job.url_normalized = normalize_url(candidate.url)
        if not job.external_id and candidate.external_id:
            job.external_id = candidate.external_id
        if not job.fingerprint_hash:
            job.fingerprint_hash = fingerprint_hash(
                title=job.title,
                company=job.company,
                location=job.location,
                job_id=job.external_id,
            )
        if job.description_status == DescriptionStatus.INSUFFICIENT.value and (
            job.description and len(job.description) >= 120
        ):
            job.description_status = DescriptionStatus.OK.value
        self.db.flush()


def _guess_work_mode(location: str | None, description: str | None) -> str:
    haystack = f"{location or ''} {description or ''}".lower()
    if "remote" in haystack or "uzaktan" in haystack:
        return WorkMode.REMOTE.value
    if "hybrid" in haystack or "hibrit" in haystack:
        return WorkMode.HYBRID.value
    if "on-site" in haystack or "onsite" in haystack or "ofis" in haystack:
        return WorkMode.ONSITE.value
    return WorkMode.UNKNOWN.value
