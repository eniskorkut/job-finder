"""Structured LLM contracts.

Every model output is validated with Pydantic before it reaches the database;
a model is never trusted to return sane JSON.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DimensionStatus = Literal["match", "partial", "mismatch", "unknown"]

CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class DimensionMatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: DimensionStatus = "unknown"
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def _trim(cls, value: str) -> str:
        return " ".join((value or "").split())[:600]


class LlmMatchResult(BaseModel):
    """CV <-> job requirement fit. Never a hiring probability."""

    model_config = ConfigDict(extra="ignore")

    match_score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list, max_length=40)
    missing_skills: list[str] = Field(default_factory=list, max_length=40)
    experience_match: DimensionMatch = Field(default_factory=DimensionMatch)
    location_match: DimensionMatch = Field(default_factory=DimensionMatch)
    work_mode_match: DimensionMatch = Field(default_factory=DimensionMatch)
    title_match: DimensionMatch = Field(default_factory=DimensionMatch)
    reasoning: str = ""
    insufficient_information: bool = False

    @field_validator("matched_skills", "missing_skills")
    @classmethod
    def _clean_skills(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            text = " ".join(str(value).split())[:60]
            if text and text.lower() not in {item.lower() for item in cleaned}:
                cleaned.append(text)
        return cleaned[:40]

    @field_validator("reasoning")
    @classmethod
    def _trim_reasoning(cls, value: str) -> str:
        return (value or "").strip()[:2000]


class LlmCVProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skills: list[str] = Field(default_factory=list, max_length=60)
    languages: list[str] = Field(default_factory=list, max_length=20)
    education: list[str] = Field(default_factory=list, max_length=20)
    experience: list[str] = Field(default_factory=list, max_length=30)
    years_of_experience: float | None = Field(default=None, ge=0, le=70)
    technologies: list[str] = Field(default_factory=list, max_length=60)
    domains: list[str] = Field(default_factory=list, max_length=30)
    certifications: list[str] = Field(default_factory=list, max_length=30)
    preferred_roles_from_cv: list[str] = Field(default_factory=list, max_length=20)

    @field_validator(
        "skills",
        "languages",
        "education",
        "experience",
        "technologies",
        "domains",
        "certifications",
        "preferred_roles_from_cv",
    )
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            text = " ".join(str(value).split())[:160]
            if text and text.lower() not in {item.lower() for item in cleaned}:
                cleaned.append(text)
        return cleaned


class LlmOutputError(ValueError):
    """The model did not return usable JSON for the requested schema."""

    def __init__(self, message: str, *, raw: str = "") -> None:
        super().__init__(message)
        self.raw_excerpt = raw[:500]


def extract_json_object(raw: str) -> dict:
    """Pull the first JSON object out of a model response.

    Handles ```json fences, leading prose and trailing commentary, but never
    executes or interprets anything from the text.
    """
    if not raw or not raw.strip():
        raise LlmOutputError("Model boş yanıt döndürdü.")

    text = CODE_FENCE_RE.sub("", raw.strip()).strip()
    for candidate in (text, _first_balanced_object(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise LlmOutputError("Model yanıtı geçerli bir JSON nesnesi içermiyor.", raw=raw)


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
