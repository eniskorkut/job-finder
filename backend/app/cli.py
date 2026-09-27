"""Job Hunter command line tools.

Examples
--------
python -m app.cli create-user --username enis --email enis@example.com --owner
python -m app.cli invite --email partner@example.com --ttl-hours 48
python -m app.cli seed
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timezone

from app.core.config import settings
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.repositories.integrations import SyncHistoryRepository
from app.repositories.invitations import InvitationRepository
from app.repositories.users import UserRepository
from app.seed import DEFAULT_DEMO_PASSWORD, seed_demo_data
from app.services.invitation_service import InvitationService
from app.services.user_service import UserService


def _prompt_password(label: str = "Parola") -> str:
    first = getpass.getpass(f"{label}: ")
    second = getpass.getpass(f"{label} (tekrar): ")
    if first != second:
        print("Parolalar eşleşmiyor.", file=sys.stderr)
        raise SystemExit(1)
    if len(first) < 10:
        print("Parola en az 10 karakter olmalı.", file=sys.stderr)
        raise SystemExit(1)
    return first


def create_user(args: argparse.Namespace) -> int:
    password = args.password or _prompt_password()
    db = SessionLocal()
    try:
        user = UserService(db).create_user(
            username=args.username,
            email=args.email,
            password=password,
            full_name=args.full_name,
            make_owner=args.owner,
        )
        db.commit()
        print(f"Kullanıcı oluşturuldu: {user.username} <{user.email}> (rol: {user.role})")
        if args.owner:
            print("Bu kullanıcı owner olarak işaretlendi ve davet gönderebilir.")
        return 0
    except AppError as exc:
        db.rollback()
        print(f"Hata: {exc.detail['message']}", file=sys.stderr)
        return 1
    finally:
        db.close()


def invite(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        users = UserRepository(db)
        inviter = users.get_by_identifier(args.invited_by) if args.invited_by else None
        if inviter is None:
            owner = next(
                (user for user in users.list_all() if user.role == "owner"), None
            )
            inviter = owner
        if inviter is None:
            print("Davet gönderecek owner kullanıcı bulunamadı.", file=sys.stderr)
            return 1

        invitation, token = InvitationService(db).create_invitation(
            inviter,
            email=args.email,
            note=args.note,
            expires_in_hours=args.ttl_hours,
        )
        db.commit()
        url = f"{settings.frontend_url.rstrip('/')}/invite/{token}"
        expires = invitation.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        print("Davet oluşturuldu (tek kullanımlık, süreli):")
        print(f"  Davet eden : {inviter.username}")
        print(f"  E-posta    : {invitation.email}")
        print(f"  Bitiş      : {expires.isoformat()}")
        print(f"  Bağlantı   : {url}")
        print("\nBu bağlantı yalnızca bir kez kullanılabilir ve süresi dolunca geçersiz olur.")
        return 0
    except AppError as exc:
        db.rollback()
        print(f"Hata: {exc.detail['message']}", file=sys.stderr)
        return 1
    finally:
        db.close()


def list_users(_: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        users = UserRepository(db).list_all()
        if not users:
            print("Kayıtlı kullanıcı yok. Önce create-user komutunu çalıştırın.")
            return 0
        print(f"{'kullanıcı':<20} {'e-posta':<35} {'rol':<8} son giriş")
        for user in users:
            last = user.last_login_at.strftime("%Y-%m-%d %H:%M") if user.last_login_at else "-"
            print(f"{user.username:<20} {user.email:<35} {user.role:<8} {last}")
        return 0
    finally:
        db.close()


def list_invitations(_: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        invitations = InvitationRepository(db).list_all()
        if not invitations:
            print("Davet kaydı yok.")
            return 0
        for invitation in invitations:
            expires_at = invitation.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if invitation.used_at is not None:
                status = "kullanıldı"
            elif expires_at <= now:
                status = "süresi doldu"
            else:
                status = "bekliyor"
            print(
                f"{invitation.email:<35} {status:<14} bitiş: {expires_at.strftime('%Y-%m-%d %H:%M')}"
            )
        return 0
    finally:
        db.close()


def purge_invitations(_: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        removed = InvitationService(db).purge_expired()
        db.commit()
        print(f"{removed} süresi dolmuş davet silindi.")
        return 0
    finally:
        db.close()


def seed(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        result = seed_demo_data(
            db,
            user1_password=args.password or DEFAULT_DEMO_PASSWORD,
            user2_password=args.password or DEFAULT_DEMO_PASSWORD,
        )
        print("Mock veriler hazır.")
        for user in result["users"]:
            print(f"  {user['username']} / {user['password']}  ({user['jobs']} örnek ilan)")
        print(f"  {result['note']}")
        if result["created_users"]:
            print(f"  Yeni oluşturulan kullanıcılar: {', '.join(result['created_users'])}")
        return 0
    except AppError as exc:
        db.rollback()
        print(f"Hata: {exc.detail['message']}", file=sys.stderr)
        return 1
    finally:
        db.close()


def status(_: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        users = UserRepository(db).list_all()
        print(f"Veritabanı: {settings.database_url}")
        print(f"Kullanıcı sayısı: {len(users)}")
        for user in users:
            jobs = SyncHistoryRepository(db).latest_for_user(user.id)
            last = jobs.started_at.strftime("%Y-%m-%d %H:%M") if jobs else "-"
            print(f"  - {user.username}: son tarama {last}")
        print(f"Veri dizini: {settings.data_path}")
        return 0
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="Job Hunter CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create-user", help="Yeni kullanıcı oluştur")
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--email", required=True)
    p_create.add_argument("--full-name", default=None)
    p_create.add_argument("--password", default=None, help="Verilmezse güvenli şekilde sorulur")
    p_create.add_argument("--owner", action="store_true", help="İlk kullanıcı için owner rolü")
    p_create.set_defaults(func=create_user)

    p_invite = sub.add_parser("invite", help="Süreli, tek kullanımlık davet bağlantısı üret")
    p_invite.add_argument("--email", required=True)
    p_invite.add_argument("--ttl-hours", type=int, default=None)
    p_invite.add_argument("--note", default=None)
    p_invite.add_argument("--invited-by", default=None, help="Kullanıcı adı veya e-posta")
    p_invite.set_defaults(func=invite)

    sub.add_parser("list-users", help="Kullanıcıları listele").set_defaults(func=list_users)
    sub.add_parser("list-invitations", help="Davetleri listele").set_defaults(
        func=list_invitations
    )
    sub.add_parser("purge-invitations", help="Süresi dolmuş davetleri sil").set_defaults(
        func=purge_invitations
    )

    p_seed = sub.add_parser("seed", help="İki örnek kullanıcı ve mock ilanları oluştur")
    p_seed.add_argument("--password", default=None, help="İki demo kullanıcı için ortak parola")
    p_seed.set_defaults(func=seed)

    sub.add_parser("status", help="Kısa durum özeti").set_defaults(func=status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
