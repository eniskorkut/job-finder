"""Scan one mailbox and turn its job alerts into per-user job records.

Design constraints honoured here:

* one mailbox = one task with its own short-lived DB sessions (SQLAlchemy
  sessions are never shared across tasks and no transaction stays open while a
  network request is in flight),
* bounded work per run (first window + message cap), a FastAPI request never
  waits for this,
* the cursor only moves after the page it covers is committed,
* a failure in one mailbox is recorded on that mailbox only.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from typing import AsyncIterator

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.db.session import SessionLocal
from app.integrations.base import MailProviderClient, MailQuery, ScanMode
from app.integrations.errors import CursorExpiredError, ProviderAuthError, ProviderError
from app.integrations.parsing.filters import message_matches, sanitize_filters
from app.integrations.parsing.linkedin import LinkedInAlertParser
from app.models.enums import (
    ConnectionStatus,
    CursorKind,
    ErrorClass,
    ProcessedMessageStatus,
    Provider,
    SyncJobAccountStatus,
)
from app.models.mail_account import MailAccount
from app.models.sync_job import ProcessedMessage, SyncCheckpoint, SyncJob
from app.services.job_ingest_service import JobIngestService
from app.services.oauth_service import ClientFactory

logger = logging.getLogger("jobhunter.scan")

ACCESS_TOKEN_SKEW = timedelta(seconds=90)


@dataclass(slots=True)
class AccountScanOutcome:
    status: SyncJobAccountStatus = SyncJobAccountStatus.SUCCEEDED
    messages_scanned: int = 0
    jobs_found: int = 0
    jobs_new: int = 0
    jobs_duplicate: int = 0
    messages_skipped: int = 0
    error_message: str | None = None
    error_class: ErrorClass = ErrorClass.NONE
    cursor_advanced: bool = False


class ProgressTracker:
    """Atomic progress updates in their own short transaction."""

    def __init__(self, job_id: uuid.UUID, *, session_factory=SessionLocal) -> None:
        self.job_id = job_id
        self.session_factory = session_factory

    def add(
        self,
        *,
        messages_scanned: int = 0,
        jobs_found: int = 0,
        jobs_new: int = 0,
        jobs_duplicate: int = 0,
        messages_skipped: int = 0,
        errors_count: int = 0,
        accounts_processed: int = 0,
    ) -> None:
        deltas = {
            "messages_scanned": messages_scanned,
            "jobs_found": jobs_found,
            "jobs_new": jobs_new,
            "jobs_duplicate": jobs_duplicate,
            "messages_skipped": messages_skipped,
            "errors_count": errors_count,
            "accounts_processed": accounts_processed,
        }
        if not any(deltas.values()):
            return
        with self.session_factory() as session:
            session.execute(
                update(SyncJob)
                .where(SyncJob.id == self.job_id)
                .values(
                    {
                        column: getattr(SyncJob, column) + value
                        for column, value in deltas.items()
                        if value
                    }
                )
            )
            session.commit()


class MailScanService:
    """Scans exactly one mailbox for one user."""

    def __init__(
        self,
        *,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        job_id: uuid.UUID,
        client_factory: ClientFactory | None = None,
        parser: LinkedInAlertParser | None = None,
        session_factory=SessionLocal,
        now: datetime | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self.user_id = user_id
        self.account_id = account_id
        self.job_id = job_id
        self.factory = client_factory or ClientFactory()
        self.parser = parser or LinkedInAlertParser()
        self.session_factory = session_factory
        self.progress = ProgressTracker(job_id, session_factory=session_factory)
        self._origin = now
        self._cancel_check = cancel_check
        self._client_instance: MailProviderClient | None = None

    # --- session helpers ------------------------------------------------
    @contextmanager
    def _db(self):
        session: Session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[MailProviderClient]:
        client = self._client_instance
        if client is None:
            raise ProviderAuthError("İstemci hazırlanamadı.", provider="unknown")
        if hasattr(client, "__aenter__"):
            await client.__aenter__()  # type: ignore[misc]
        try:
            yield client
        finally:
            if hasattr(client, "__aexit__"):
                await client.__aexit__()  # type: ignore[misc]

    # --- main entry point ------------------------------------------------
    async def run(self) -> AccountScanOutcome:
        outcome = AccountScanOutcome()
        try:
            prepared = self._prepare()
        except ProviderAuthError as exc:
            self._mark_account_broken(ConnectionStatus.NEEDS_REAUTH.value, str(exc))
            return AccountScanOutcome(
                status=SyncJobAccountStatus.FAILED,
                error_message=str(exc),
                error_class=ErrorClass.AUTH,
            )
        except ProviderError as exc:
            return AccountScanOutcome(
                status=SyncJobAccountStatus.FAILED,
                error_message=str(exc),
                error_class=exc.error_class,
            )
        if prepared is None:
            return AccountScanOutcome(
                status=SyncJobAccountStatus.SKIPPED,
                error_message="Hesap bulunamadı veya bağlı değil.",
                error_class=ErrorClass.PERMANENT,
            )

        account, client, filters, checkpoint_snapshot = prepared
        try:
            async with self._client() as provider:
                outcome = await self._scan(
                    account=account,
                    provider=provider,
                    filters=filters,
                    checkpoint=checkpoint_snapshot,
                )
        except ProviderAuthError as exc:
            self._mark_account_broken(ConnectionStatus.NEEDS_REAUTH.value, str(exc))
            outcome = AccountScanOutcome(
                status=SyncJobAccountStatus.FAILED,
                error_message=str(exc),
                error_class=ErrorClass.AUTH,
            )
        except ProviderError as exc:
            self._mark_account_broken(ConnectionStatus.ERROR.value, str(exc))
            outcome = AccountScanOutcome(
                status=SyncJobAccountStatus.FAILED,
                error_message=str(exc),
                error_class=exc.error_class,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Tarama beklenmeyen hata verdi: %s", exc)
            outcome = AccountScanOutcome(
                status=SyncJobAccountStatus.FAILED,
                error_message=f"Beklenmeyen hata: {type(exc).__name__}",
                error_class=ErrorClass.TRANSIENT,
            )
        return outcome

    # --- preparation -----------------------------------------------------
    def _prepare(self) -> tuple[MailAccount, MailProviderClient, dict, SyncCheckpoint] | None:
        with self._db() as db:
            account = db.get(MailAccount, self.account_id)
            if account is None or account.user_id != self.user_id:
                return None
            if account.status not in {
                ConnectionStatus.CONNECTED.value,
                ConnectionStatus.ERROR.value,
                ConnectionStatus.NEEDS_REAUTH.value,
            }:
                return None

            if account.provider == Provider.GMAIL.value and not settings.google_oauth_configured:
                raise ProviderAuthError(
                    "Google / Gmail istemci bilgileri sistemde yapılandırılmamış.",
                    provider=account.provider,
                )
            if account.provider == Provider.OUTLOOK.value and not settings.microsoft_oauth_configured:
                raise ProviderAuthError(
                    "Microsoft / Outlook istemci bilgileri sistemde yapılandırılmamış.",
                    provider=account.provider,
                )

            client = self.factory.build(
                provider=account.provider,
            )
            self._client_instance = client

            from app.repositories.sync_jobs import CheckpointRepository

            checkpoint = CheckpointRepository(db).get_or_create(self.user_id, account.id)
            filters = sanitize_filters(account.filters)
            db.expunge(account)
            db.expunge(checkpoint)
        return account, client, filters, checkpoint

    # --- scan loop --------------------------------------------------------
    async def _scan(
        self,
        *,
        account: MailAccount,
        provider: MailProviderClient,
        filters: dict,
        checkpoint: SyncCheckpoint,
    ) -> AccountScanOutcome:
        outcome = AccountScanOutcome()
        now = self._origin or datetime.now(timezone.utc)
        initial_window_start = now - timedelta(days=settings.sync_initial_window_days)

        cursor = checkpoint.cursor_value
        mode = ScanMode.INCREMENTAL if cursor else ScanMode.INITIAL
        if not checkpoint.initial_sync_completed:
            mode = ScanMode.INITIAL
            cursor = None

        access_token = await self._ensure_access_token(provider, account)
        semaphore = asyncio.Semaphore(max(1, settings.sync_mailbox_concurrency))

        query = MailQuery(
            senders=filters.get("senders") or [],
            subjects=filters.get("subjects") or [],
            since=initial_window_start if mode is ScanMode.INITIAL else None,
            limit=(
                settings.sync_initial_max_messages
                if mode is ScanMode.INITIAL
                else settings.sync_max_results_per_run
            ),
            batch_size=settings.sync_batch_size,
        )

        processed = 0
        pages = 0
        max_pages = 50
        cursor_resets = 0

        while pages < max_pages:
            if self._cancel_check is not None and self._cancel_check():
                outcome.status = SyncJobAccountStatus.SKIPPED
                outcome.error_message = "Kullanıcı taramayı iptal etti."
                return outcome
            pages += 1
            try:
                page = await provider.fetch_page(
                    access_token=access_token,
                    mode=mode,
                    query=query,
                    cursor=cursor,
                )
            except CursorExpiredError:
                if cursor_resets >= 1:
                    raise
                cursor_resets += 1
                logger.info(
                    "Cursor süresi doldu, sınırlı yeniden tarama yapılıyor (account=%s)",
                    account.id,
                )
                self._reset_cursor(account.id, reason="Cursor geçersiz; yeniden tarama.")
                mode = ScanMode.INITIAL
                cursor = None
                query.since = initial_window_start
                continue

            refs = list(page.refs)
            fresh_refs = self._filter_unprocessed(account.id, refs)
            deduplicated = len(refs) - len(fresh_refs)

            remaining = max(0, query.limit - processed)
            messages = []
            if page.messages:
                wanted = set(fresh_refs)
                messages = [m for m in page.messages if m.external_id in wanted][:remaining]
            elif fresh_refs and remaining:
                messages = await self._fetch_many(
                    provider, access_token, fresh_refs[:remaining], semaphore
                )

            for message in messages:
                if mode is ScanMode.INITIAL and message.received_at < initial_window_start:
                    self._record_message(
                        account.id,
                        message,
                        status=ProcessedMessageStatus.SKIPPED,
                        reason="outside_window",
                        jobs_found=0,
                    )
                    outcome.messages_skipped += 1
                    continue
                stats = self._handle_message(account, message, filters)
                outcome.messages_scanned += 1
                outcome.jobs_found += stats["jobs_found"]
                outcome.jobs_new += stats["jobs_new"]
                outcome.jobs_duplicate += stats["jobs_duplicate"]
                if stats["skipped"]:
                    outcome.messages_skipped += 1
                self.progress.add(
                    messages_scanned=1,
                    jobs_found=stats["jobs_found"],
                    jobs_new=stats["jobs_new"],
                    jobs_duplicate=stats["jobs_duplicate"],
                    messages_skipped=1 if stats["skipped"] else 0,
                )
                processed += 1

            if deduplicated:
                self.progress.add(messages_skipped=deduplicated)
                outcome.messages_skipped += deduplicated

            checkpoint_cursor = page.checkpoint_cursor
            if checkpoint_cursor and (page.done or processed < query.limit):
                self._advance_checkpoint(
                    account.id,
                    cursor_kind=page.cursor_kind,
                    cursor_value=checkpoint_cursor,
                    last_message_at=max(
                        (message.received_at for message in messages), default=None
                    ),
                    initial_sync_completed=page.done or mode is ScanMode.INCREMENTAL,
                )
                outcome.cursor_advanced = True

            if processed >= query.limit:
                break
            if page.done:
                break
            cursor = page.next_cursor

        self._finalize_account(account.id)
        return outcome

    # --- token handling ---------------------------------------------------
    async def _ensure_access_token(
        self, provider: MailProviderClient, account: MailAccount
    ) -> str:
        with self._db() as db:
            row = db.get(MailAccount, account.id)
            access_token = (
                decrypt_secret(row.access_token_encrypted)
                if row.access_token_encrypted
                else None
            )
            expires_at = row.token_expires_at
            refresh_token = (
                decrypt_secret(row.refresh_token_encrypted)
                if row.refresh_token_encrypted
                else None
            )
            cache = (
                decrypt_secret(row.token_cache_encrypted)
                if row.token_cache_encrypted
                else None
            )
            provider_account_id = row.provider_account_id

        moment = self._origin or datetime.now(timezone.utc)
        fresh_enough = False
        if access_token:
            if expires_at is None:
                fresh_enough = True
            else:
                aware = (
                    expires_at
                    if expires_at.tzinfo is not None
                    else expires_at.replace(tzinfo=timezone.utc)
                )
                fresh_enough = aware > moment + ACCESS_TOKEN_SKEW
        if access_token and fresh_enough:
            return access_token

        tokens = await provider.refresh(
            refresh_token=refresh_token,
            cache=cache,
            account_id=provider_account_id,
        )
        with self._db() as db:
            row = db.get(MailAccount, account.id)
            if row is None:
                raise ProviderAuthError("Hesap silinmiş.", provider=account.provider)
            row.access_token_encrypted = encrypt_secret(tokens.access_token)
            if tokens.refresh_token:
                row.refresh_token_encrypted = encrypt_secret(tokens.refresh_token)
            if tokens.cache_serialized:
                row.token_cache_encrypted = encrypt_secret(tokens.cache_serialized)
            row.token_expires_at = tokens.expires_at
            if tokens.scopes:
                row.scopes = list(tokens.scopes)
        return tokens.access_token

    # --- message helpers --------------------------------------------------
    async def _fetch_many(
        self,
        provider: MailProviderClient,
        access_token: str,
        message_ids: list[str],
        semaphore: asyncio.Semaphore,
    ):
        async def fetch(message_id: str):
            async with semaphore:
                try:
                    return await provider.fetch_message(
                        access_token=access_token, message_id=message_id
                    )
                except ProviderError as exc:
                    logger.warning(
                        "Mesaj alınamadı (%s): %s", message_id, exc
                    )
                    return None

        results = await asyncio.gather(*(fetch(mid) for mid in message_ids))
        return [message for message in results if message is not None]

    def _handle_message(self, account: MailAccount, message, filters: dict) -> dict:
        ok, reason = message_matches(
            sender=message.sender, subject=message.subject, filters=filters
        )
        if not ok:
            self._record_message(
                account.id,
                message,
                status=ProcessedMessageStatus.SKIPPED,
                reason=reason,
                jobs_found=0,
            )
            return {"jobs_found": 0, "jobs_new": 0, "jobs_duplicate": 0, "skipped": True}

        candidates = self.parser.parse(message)
        if not candidates:
            # A LinkedIn alert with no job link is "0 jobs", not an error.
            self._record_message(
                account.id,
                message,
                status=ProcessedMessageStatus.SKIPPED,
                reason="no_jobs",
                jobs_found=0,
            )
            return {"jobs_found": 0, "jobs_new": 0, "jobs_duplicate": 0, "skipped": True}

        with self._db() as db:
            try:
                result = JobIngestService(db, now=self._origin).ingest_message(
                    user_id=self.user_id,
                    account=account,
                    message=message,
                    candidates=candidates,
                )
            except IntegrityError:
                db.rollback()
                result = None

        if result is None:
            return {"jobs_found": 0, "jobs_new": 0, "jobs_duplicate": 0, "skipped": True}

        jobs_new = result.jobs_new
        self._record_message(
            account.id,
            message,
            status=ProcessedMessageStatus.PROCESSED,
            reason=None,
            jobs_found=result.jobs_found,
        )
        return {
            "jobs_found": result.jobs_found,
            "jobs_new": jobs_new,
            "jobs_duplicate": result.jobs_duplicate,
            "skipped": False,
        }

    def _filter_unprocessed(self, account_id: uuid.UUID, refs: list[str]) -> list[str]:
        if not refs:
            return []
        with self._db() as db:
            rows = db.execute(
                select(ProcessedMessage.provider_message_id).where(
                    ProcessedMessage.mail_account_id == account_id,
                    ProcessedMessage.provider_message_id.in_(refs),
                )
            ).scalars()
            already = set(rows)
        return [ref for ref in refs if ref not in already]

    def _record_message(
        self,
        account_id: uuid.UUID,
        message,
        *,
        status: ProcessedMessageStatus,
        reason: str | None,
        jobs_found: int,
    ) -> None:
        with self._db() as db:
            try:
                db.add(
                    ProcessedMessage(
                        user_id=self.user_id,
                        mail_account_id=account_id,
                        provider_message_id=message.external_id,
                        status=status.value,
                        reason=reason,
                        subject=(message.subject or "")[:500] or None,
                        sender=(message.sender or "")[:320] or None,
                        received_at=message.received_at,
                        jobs_found=jobs_found,
                    )
                )
                db.flush()
            except IntegrityError:
                # Already handled by a concurrent/previous run: idempotent.
                db.rollback()

    # --- persistence ------------------------------------------------------
    def _advance_checkpoint(
        self,
        account_id: uuid.UUID,
        *,
        cursor_kind: CursorKind,
        cursor_value: str | None,
        last_message_at: datetime | None,
        initial_sync_completed: bool,
    ) -> None:
        from app.repositories.sync_jobs import CheckpointRepository

        with self._db() as db:
            checkpoint = CheckpointRepository(db).get_or_create(self.user_id, account_id)
            CheckpointRepository(db).advance(
                checkpoint,
                cursor_kind=cursor_kind,
                cursor_value=cursor_value,
                last_message_at=last_message_at,
                initial_sync_completed=initial_sync_completed,
            )
            account = db.get(MailAccount, account_id)
            if account is not None:
                account.last_synced_at = datetime.now(timezone.utc)
                if initial_sync_completed:
                    account.initial_sync_completed = True

    def _reset_cursor(self, account_id: uuid.UUID, *, reason: str) -> None:
        from app.repositories.sync_jobs import CheckpointRepository

        with self._db() as db:
            checkpoint = CheckpointRepository(db).get_or_create(self.user_id, account_id)
            checkpoint.cursor_kind = CursorKind.NONE.value
            checkpoint.cursor_value = None
            CheckpointRepository(db).advance(
                checkpoint,
                cursor_kind=CursorKind.NONE,
                cursor_value=None,
                initial_sync_completed=False,
            )
            checkpoint.last_error = reason[:1000]

    def _mark_account_broken(self, status: str, message: str) -> None:
        with self._db() as db:
            account = db.get(MailAccount, self.account_id)
            if account is None:
                return
            account.status = status
            account.last_error = message[:500]
            from app.repositories.sync_jobs import CheckpointRepository

            checkpoint = CheckpointRepository(db).get_or_create(self.user_id, self.account_id)
            CheckpointRepository(db).mark_failure(
                checkpoint,
                message=message,
                error_class=ErrorClass.AUTH
                if status == ConnectionStatus.NEEDS_REAUTH.value
                else ErrorClass.TRANSIENT,
            )

    def _finalize_account(self, account_id: uuid.UUID) -> None:
        with self._db() as db:
            account = db.get(MailAccount, account_id)
            if account is not None and account.status == ConnectionStatus.ERROR.value:
                account.status = ConnectionStatus.CONNECTED.value
                account.last_error = None
