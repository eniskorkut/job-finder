"""Freshness, posted date calculation, and availability evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import settings


@dataclass(slots=True)
class DateEvaluationResult:
    effective_posted_at: datetime
    posted_at_source: str  # "json_ld", "html_meta", "email_date", "discovery_date"
    posted_at_confidence: str  # "high", "medium", "low"


@dataclass(slots=True)
class FreshnessResult:
    freshness_status: str  # "fresh", "aging", "stale", "expired"
    availability_status: str  # "active", "closed", "possibly_closed", "removed", "unknown"
    age_days: float
    should_auto_score: bool


def evaluate_posted_at(
    *,
    json_ld_date: datetime | None = None,
    html_meta_date: datetime | None = None,
    email_received_at: datetime | None = None,
    discovered_at: datetime | None = None,
    now: datetime | None = None,
) -> DateEvaluationResult:
    """Determine effective posted_at date, source, and confidence according to strict precedence rules:
    JSON-LD date (high) > HTML meta date (medium) > Email received date (low) > Discovered date (low).
    Future dates beyond 24h are rejected, triggering fallback to email or discovery date.
    """
    current_time = now or datetime.now(timezone.utc)
    max_future_cutoff = current_time + timedelta(hours=24)

    def _sanitize(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        # Dates further than 24 hours into the future are rejected (bad source data)
        if dt_utc > max_future_cutoff:
            return None
        return dt_utc

    # 1. JSON-LD datePosted
    sanitized_json = _sanitize(json_ld_date)
    if sanitized_json is not None:
        return DateEvaluationResult(
            effective_posted_at=sanitized_json,
            posted_at_source="json_ld",
            posted_at_confidence="high",
        )

    # 2. HTML meta / time tag
    sanitized_meta = _sanitize(html_meta_date)
    if sanitized_meta is not None:
        return DateEvaluationResult(
            effective_posted_at=sanitized_meta,
            posted_at_source="html_meta",
            posted_at_confidence="medium",
        )

    # 3. Email alert received date
    sanitized_email = _sanitize(email_received_at)
    if sanitized_email is not None:
        return DateEvaluationResult(
            effective_posted_at=sanitized_email,
            posted_at_source="email_date",
            posted_at_confidence="low",
        )

    # 4. Discovered date
    sanitized_discovery = _sanitize(discovered_at) or current_time
    return DateEvaluationResult(
        effective_posted_at=sanitized_discovery,
        posted_at_source="discovery_date",
        posted_at_confidence="low",
    )


def calculate_freshness(
    *,
    effective_posted_at: datetime | None,
    valid_through: datetime | None = None,
    is_closed: bool = False,
    availability_status: str | None = None,
    now: datetime | None = None,
    max_age_days: int | None = None,
) -> FreshnessResult:
    """Calculate freshness category (fresh: 0-3d, aging: 4-7d, stale: 8-14d, expired: >14d or closed)
    and determine whether the job is eligible for automatic LLM scoring.
    """
    current_time = now or datetime.now(timezone.utc)
    max_age = max_age_days if max_age_days is not None else settings.job_max_age_days

    # Explicitly closed, removed, or possibly_closed
    if availability_status in {"possibly_closed", "removed", "closed"}:
        return FreshnessResult(
            freshness_status="expired",
            availability_status=availability_status,
            age_days=0.0,
            should_auto_score=False,
        )

    if is_closed:
        return FreshnessResult(
            freshness_status="expired",
            availability_status="closed",
            age_days=0.0,
            should_auto_score=False,
        )

    # Check broken valid_through (< effective_posted_at)
    cleaned_valid_through = valid_through
    if cleaned_valid_through is not None and effective_posted_at is not None:
        if cleaned_valid_through.tzinfo is None:
            cleaned_valid_through = cleaned_valid_through.replace(tzinfo=timezone.utc)
        eff_tz = effective_posted_at if effective_posted_at.tzinfo else effective_posted_at.replace(tzinfo=timezone.utc)
        if cleaned_valid_through < eff_tz:
            # Broken validThrough before posted date; ignore it
            cleaned_valid_through = None

    # Expired via validThrough
    if cleaned_valid_through is not None:
        if cleaned_valid_through.tzinfo is None:
            cleaned_valid_through = cleaned_valid_through.replace(tzinfo=timezone.utc)
        if cleaned_valid_through < current_time:
            return FreshnessResult(
                freshness_status="expired",
                availability_status="closed",
                age_days=max(0.0, (current_time - cleaned_valid_through).total_seconds() / 86400),
                should_auto_score=False,
            )

    # Calculate age from effective_posted_at
    if effective_posted_at is not None:
        if effective_posted_at.tzinfo is None:
            effective_posted_at = effective_posted_at.replace(tzinfo=timezone.utc)
        age_seconds = max(0.0, (current_time - effective_posted_at).total_seconds())
        age_days = age_seconds / 86400.0
    else:
        age_days = 0.0

    fresh_cutoff = settings.job_fresh_days
    aging_cutoff = settings.job_aging_days
    stale_cutoff = settings.job_stale_days

    if age_days <= fresh_cutoff:
        freshness_status = "fresh"
    elif age_days <= aging_cutoff:
        freshness_status = "aging"
    elif age_days <= stale_cutoff:
        freshness_status = "stale"
    else:
        freshness_status = "expired"

    eff_availability = availability_status or "active"
    should_auto_score = (freshness_status != "expired") and (age_days <= max_age)

    return FreshnessResult(
        freshness_status=freshness_status,
        availability_status=eff_availability,
        age_days=round(age_days, 1),
        should_auto_score=should_auto_score,
    )
