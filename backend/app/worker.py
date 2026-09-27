"""Durable scan worker.

Run it next to the API (a second terminal):

    python -m app.worker                 # follow the queue forever
    python -m app.worker --once          # process one job and exit (dev/tests)
    python -m app.worker --poll-seconds 1

The API only enqueues jobs and answers 202; this process owns provider calls,
concurrency limits, heartbeats and lease recovery. Restarting it is safe: a
job whose lease expired is requeued and its mailboxes are idempotent because
every processed message is recorded in ``processed_messages``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import inspect, text

from app.core.config import settings
from app.db.session import engine
from app.services.sync_job_service import SyncRunner, default_worker_id

logger = logging.getLogger("jobhunter.worker")


def _check_schema() -> bool:
    tables = set(inspect(engine).get_table_names())
    if "sync_jobs" not in tables:
        print(
            "Veritabanı şeması güncel değil. Önce 'alembic upgrade head' çalıştırın.",
            file=sys.stderr,
        )
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.worker", description="Job Hunter tarama işçisi")
    parser.add_argument("--once", action="store_true", help="Tek iş işleyip çık")
    parser.add_argument("--poll-seconds", type=float, default=None, help="Boş kuyruk bekleme süresi")
    parser.add_argument("--verbose", action="store_true", help="Ayrıntılı günlük")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if not _check_schema():
        return 1

    with engine.connect() as connection:
        journal = connection.execute(text("PRAGMA journal_mode")).scalar_one_or_none()
    runner = SyncRunner()
    logger.info(
        "Tarama işçisi hazır (worker=%s, sqlite_journal=%s, max_mailbox=%s, per_mailbox=%s)",
        default_worker_id(),
        journal,
        settings.sync_max_active_mailboxes,
        settings.sync_mailbox_concurrency,
    )

    try:
        processed = asyncio.run(
            runner.run_forever(once=args.once, poll_seconds=args.poll_seconds)
        )
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        logger.info("İşçi durduruldu.")
        return 0
    if args.once:
        logger.info("Tek seferlik çalışma bitti (%s iş).", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
