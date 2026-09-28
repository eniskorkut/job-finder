from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.preferences import UserPreference
from app.models.user import User
from app.repositories.preferences import PreferenceRepository
from app.schemas.preferences import PreferencesUpdate
from app.services.scheduler_service import SchedulerService, clamp_interval, utcnow


class PreferenceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.preferences = PreferenceRepository(db)
        self.scheduler = SchedulerService(now=utcnow())

    def get(self, user: User) -> UserPreference:
        preference = self.preferences.get_or_create(user)
        self._ensure_plan(preference)
        return preference

    def update(self, user: User, payload: PreferencesUpdate) -> UserPreference:
        preference = self.preferences.get_or_create(user)
        data = payload.model_dump(exclude_unset=True, exclude_none=True)
        was_enabled = bool(preference.daily_scan_enabled)
        previous_interval = preference.scan_interval_hours

        for field, value in data.items():
            setattr(preference, field, value)

        if "scan_interval_hours" in data:
            preference.scan_interval_hours = clamp_interval(preference.scan_interval_hours)
        if "daily_scan_enabled" in data:
            if preference.daily_scan_enabled and not was_enabled:
                # First plan starts one interval from now; "Şimdi Tara" is the
                # immediate path and the UI shows the exact next run.
                self.scheduler.plan_next_scan(preference, from_time=utcnow())
                preference.auto_scan_failures = 0
            elif not preference.daily_scan_enabled:
                preference.next_scan_at = None
        elif "scan_interval_hours" in data and preference.daily_scan_enabled:
            if preference.scan_interval_hours != previous_interval:
                base = preference.last_auto_scan_at or utcnow()
                self.scheduler.plan_next_scan(preference, from_time=base)

        self.db.flush()
        return preference

    def _ensure_plan(self, preference: UserPreference) -> None:
        """Keep the stored plan consistent when the row predates phase 3."""
        if not preference.daily_scan_enabled:
            if preference.next_scan_at is not None:
                preference.next_scan_at = None
                self.db.flush()
            return
        if preference.next_scan_at is None:
            self.scheduler.plan_next_scan(preference, from_time=utcnow())
            self.db.flush()
