"""Durable scan worker.

Run it next to the API (a second terminal):

    python -m app.worker                 # follow the queue forever
    python -m app.worker --once          # process one job and exit (dev/tests)
    python -m app.worker --poll-seconds 1

The API only enqueues jobs and answers 202; this process owns provider calls,
concurrency limits, heartbeats and lease recovery, and it also runs the
per-user scheduler (no fourth process). Restarting it is safe: a job whose
lease expired is requeued, its mailboxes are idempotent (``processed_messages``)
and its scoring items are claimed atomically.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.logging import install_secret_filter
from app.db.session import engine
from app.integrations.deepseek import DeepSeekScoringClient
from app.integrations.telegram import TelegramClient
from app.services.sync_job_service import SyncRunner, default_worker_id

logger = logging.getLogger("jobhunter.worker")


def _check_schema() -> bool:
    tables = set(inspect(engine).get_table_names())
    required = {
        "sync_jobs",
        "scoring_items",
        "cv_profiles",
        "telegram_integrations",
        "job_web_sources",
        "enrichment_items",
    }
    missing = required - tables
    if missing:
        print(
            "Veritabanı şeması güncel değil (eksik: "
            + ", ".join(sorted(missing))
            + "). Önce 'alembic upgrade head' çalıştırın.",
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


async def run_worker(
    runner: SyncRunner,
    *,
    once: bool = False,
    poll_seconds: float | None = None,
    shutdown_event: asyncio.Event | None = None,
) -> int:
    event = shutdown_event or asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_signal(sig_name: str) -> None:
        logger.info("Kapatma sinyali alındı (%s), işçi durduruluyor...", sig_name)
        event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig.name: _on_signal(s))
        except (NotImplementedError, AttributeError, RuntimeError):
            try:
                signal.signal(sig, lambda _signum, _frame, s=sig.name: _on_signal(s))
            except Exception:
                pass

    try:
        return await runner.run_forever(
            once=once, poll_seconds=poll_seconds, shutdown_event=event
        )
    finally:
        await runner.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    install_secret_filter()
    if not _check_schema():
        return 1

    with engine.connect() as connection:
        journal = connection.execute(text("PRAGMA journal_mode")).scalar_one_or_none()
    llm = DeepSeekScoringClient()
    runner = SyncRunner(
        llm_factory=DeepSeekScoringClient,
        telegram_factory=TelegramClient,
    )
    logger.info(
        "İşçi hazır (worker=%s, sqlite_journal=%s, max_mailbox=%s, per_mailbox=%s, "
        "llm=%s, llm_configured=%s, concurrency=%s, scheduler=%s/%ss)",
        default_worker_id(),
        journal,
        settings.sync_max_active_mailboxes,
        settings.sync_mailbox_concurrency,
        llm.model or "-",
        llm.configured,
        llm.describe()["max_concurrency"],
        settings.scheduler_enabled,
        settings.scheduler_poll_seconds,
    )

    try:
        processed = asyncio.run(
            run_worker(runner, once=args.once, poll_seconds=args.poll_seconds)
        )
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        logger.info("İşçi durduruldu.")
        return 0
    if args.once:
        logger.info("Tek seferlik çalışma bitti (%s iş).", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
