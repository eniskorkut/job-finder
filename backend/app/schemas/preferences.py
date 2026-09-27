from __future__ import annotations

from pydantic import Field, field_validator

from app.models.enums import WorkMode
from app.schemas.common import ORMModel


class PreferencesRead(ORMModel):
    desired_titles: list[str]
    locations: list[str]
    work_modes: list[str]
    keywords_include: list[str]
    keywords_exclude: list[str]
    min_match_score: int
    daily_scan_enabled: bool
    scan_interval_hours: int
    politeness_delay_seconds: int
    notify_telegram: bool


class PreferencesUpdate(ORMModel):
    desired_titles: list[str] | None = Field(default=None, max_length=25)
    locations: list[str] | None = Field(default=None, max_length=25)
    work_modes: list[str] | None = Field(default=None, max_length=3)
    keywords_include: list[str] | None = Field(default=None, max_length=25)
    keywords_exclude: list[str] | None = Field(default=None, max_length=25)
    min_match_score: int | None = Field(default=None, ge=0, le=100)
    daily_scan_enabled: bool | None = None
    scan_interval_hours: int | None = Field(default=None, ge=1, le=168)
    politeness_delay_seconds: int | None = Field(default=None, ge=0, le=600)
    notify_telegram: bool | None = None

    @field_validator("work_modes")
    @classmethod
    def _valid_modes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        allowed = {mode.value for mode in WorkMode}
        cleaned = [item.strip().lower() for item in value if item and item.strip()]
        invalid = [item for item in cleaned if item not in allowed]
        if invalid:
            raise ValueError(f"Geçersiz çalışma modeli: {', '.join(invalid)}")
        return sorted(set(cleaned))

    @field_validator(
        "desired_titles", "locations", "keywords_include", "keywords_exclude"
    )
    @classmethod
    def _clean_list(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        seen: list[str] = []
        for item in value:
            cleaned = " ".join(item.split())
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen
