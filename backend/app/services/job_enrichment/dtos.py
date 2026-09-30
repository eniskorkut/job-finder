"""Data Transfer Objects for decoupled Job Enrichment."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.services.job_enrichment.html_parser import ExtractedJobData


@dataclass(slots=True)
class ExistingWebSourceCache:
    """Detached cache metadata for previously discovered web sources of a job."""
    url: str
    normalized_url: str
    etag: str | None = None
    last_modified: str | None = None
    content_hash: str | None = None
    selected_as_canonical: bool = False
    http_status: int | None = None


@dataclass(slots=True)
class JobEnrichmentSnapshot:
    """Detached snapshot of a job posting taken before running network operations."""
    job_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    company: str
    description: str | None
    description_status: str
    posted_at: datetime | None
    posted_at_source: str | None
    posted_at_confidence: str | None
    valid_through: datetime | None
    email_received_at: datetime | None
    discovered_at: datetime
    freshness_status: str
    availability_status: str
    enrichment_status: str
    content_hash: str | None
    canonical_url: str | None
    company_job_url: str | None
    application_url: str | None
    linkedin_url: str | None
    url: str | None
    last_enriched_at: datetime | None
    last_verified_at: datetime | None
    work_mode: str = "unknown"
    location: str | None = None
    employment_type: str | None = None
    existing_sources: list[ExistingWebSourceCache] = field(default_factory=list)


@dataclass(slots=True)
class DiscoveredWebSourceDTO:
    """Detached data representing a discovered web source."""
    url: str
    normalized_url: str
    host: str
    source_type: str
    trust_level: int
    match_confidence: str
    title: str | None
    snippet: str | None
    http_status: int | None
    content_hash: str | None
    selected_as_canonical: bool
    parser_source: str = "unknown"
    etag: str | None = None
    last_modified: str | None = None


@dataclass(slots=True)
class EnrichmentCandidate:
    """Internal candidate representation during web fetch and ranking."""
    url: str
    normalized_url: str
    host: str
    source_type: str
    trust_level: int
    match_confidence: str
    title: str | None
    extracted_data: ExtractedJobData | None
    http_status: int | None
    content_hash: str | None
    parser_source: str = "unknown"
    etag: str | None = None
    last_modified: str | None = None
    is_not_modified: bool = False


@dataclass(slots=True)
class JobEnrichmentResult:
    """Result of pure network enrichment execution, ready for persistence."""
    job_id: uuid.UUID
    status: str  # "completed", "failed", "skipped"
    enrichment_status: str  # "enriched", "skipped", "not_found", "failed"
    freshness_status: str
    availability_status: str
    canonical_url: str | None = None
    company_job_url: str | None = None
    application_url: str | None = None
    linkedin_url: str | None = None
    posted_at: datetime | None = None
    posted_at_source: str | None = None
    posted_at_confidence: str | None = None
    valid_through: datetime | None = None
    location: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    new_description: str | None = None
    new_content_hash: str | None = None
    description_updated: bool = False
    discovered_sources: list[DiscoveredWebSourceDTO] = field(default_factory=list)
    parser_source: str = "unknown"
    error_class: str | None = None
    error_message: str | None = None
    last_verified_at: datetime | None = None
    last_enriched_at: datetime | None = None


@dataclass(slots=True)
class JobEnrichmentOutcome:
    """Final outcome returned to callers after persistence."""
    job_id: uuid.UUID
    status: str  # "completed", "failed", "skipped"
    enrichment_status: str  # "enriched", "skipped", "not_found", "failed"
    freshness_status: str
    availability_status: str
    canonical_url: str | None = None
    description_updated: bool = False
    parser_source: str = "unknown"
    error_class: str | None = None
    error_message: str | None = None
