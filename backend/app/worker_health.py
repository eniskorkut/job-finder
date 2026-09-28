"""Lightweight health check for worker container."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect, text

from app.core.config import settings
from app.db.session import engine

REQUIRED_TABLES = {"sync_jobs", "scoring_items", "cv_profiles", "telegram_integrations"}


def check_health(engine_instance=None) -> int:
    try:
        # Check data directory is accessible
        data_path = Path(settings.data_dir)
        if not data_path.is_absolute():
            data_path = settings.data_path
        data_path.mkdir(parents=True, exist_ok=True)

        target_engine = engine_instance or engine
        # Check database connectivity and required tables
        with target_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            existing = set(inspect(conn).get_table_names())
            missing = REQUIRED_TABLES - existing
            if missing:
                print(f"Missing required tables: {missing}", file=sys.stderr)
                return 1
        return 0
    except Exception as exc:
        print(f"Worker health check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(check_health())
