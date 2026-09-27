"""CLI: first user creation, invitation links, listing."""

from __future__ import annotations

from app import cli
from app.repositories.users import UserRepository


def test_cli_creates_first_user_as_owner(db, capsys):
    exit_code = cli.main(
        [
            "create-user",
            "--username",
            "enis",
            "--email",
            "enis@example.com",
            "--full-name",
            "Enis Korkut",
            "--password",
            "Cok-Gizli-Parola!2026",
            "--owner",
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Kullanıcı oluşturuldu" in output
    assert "owner" in output

    user = UserRepository(db).get_by_username("enis")
    db.refresh(user)
    assert user.role == "owner"
    assert user.email == "enis@example.com"


def test_cli_rejects_duplicate_user(db, capsys):
    cli.main(
        [
            "create-user",
            "--username",
            "enis",
            "--email",
            "enis@example.com",
            "--password",
            "Cok-Gizli-Parola!2026",
            "--owner",
        ]
    )
    exit_code = cli.main(
        [
            "create-user",
            "--username",
            "enis",
            "--email",
            "baska@example.com",
            "--password",
            "Cok-Gizli-Parola!2026",
        ]
    )
    assert exit_code == 1
    assert "Hata" in capsys.readouterr().err


def test_cli_invite_prints_single_use_link(db, capsys):
    cli.main(
        [
            "create-user",
            "--username",
            "enis",
            "--email",
            "enis@example.com",
            "--password",
            "Cok-Gizli-Parola!2026",
            "--owner",
        ]
    )
    capsys.readouterr()

    exit_code = cli.main(
        ["invite", "--email", "esim@example.com", "--ttl-hours", "24"]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "http://localhost:3000/invite/" in output
    assert "tek kullanımlık" in output


def test_cli_list_users_and_status(db, capsys):
    cli.main(
        [
            "create-user",
            "--username",
            "enis",
            "--email",
            "enis@example.com",
            "--password",
            "Cok-Gizli-Parola!2026",
            "--owner",
        ]
    )
    capsys.readouterr()

    assert cli.main(["list-users"]) == 0
    assert "enis" in capsys.readouterr().out

    assert cli.main(["status"]) == 0
    assert "Kullanıcı sayısı: 1" in capsys.readouterr().out


def test_cli_seed_creates_two_users_and_mock_jobs(db, capsys):
    assert cli.main(["seed"]) == 0
    output = capsys.readouterr().out
    assert "ai_hunter" in output
    assert "data_hunter" in output
    assert "DemoParola!2026" in output

    users = UserRepository(db).list_all()
    assert {user.username for user in users} == {"ai_hunter", "data_hunter"}
