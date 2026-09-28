from __future__ import annotations

from sqlalchemy import inspect, text

from tests.conftest import alembic_config

from alembic import command

EXPECTED_TABLES = {
    "users",
    "user_preferences",
    "cvs",
    "mail_accounts",
    "jobs",
    "job_matches",
    "telegram_integrations",
    "sync_history",
    "notification_history",
    "oauth_states",
    "sessions",
    "invitations",
    "alembic_version",
    # phase 2
    "oauth_client_configs",
    "sync_jobs",
    "sync_job_accounts",
    "sync_checkpoints",
    "processed_messages",
    "job_sources",
    # phase 3
    "cv_profiles",
    "llm_usage",
    "scoring_items",
}


def test_upgrade_head_creates_every_table(tmp_path):
    from app.db.session import create_db_engine

    db_path = tmp_path / "migration.db"
    url = f"sqlite:///{db_path}"
    command.upgrade(alembic_config(url), "head")

    engine = create_db_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
        missing = EXPECTED_TABLES - tables
        assert not missing, f"Eksik tablolar: {missing}"
    finally:
        engine.dispose()


def test_upgrade_is_idempotent_and_matches_models(tmp_path):
    db_path = tmp_path / "check.db"
    url = f"sqlite:///{db_path}"
    config = alembic_config(url)
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    # Fails with an exception if the models drifted from the migration.
    command.check(config)


def test_downgrade_removes_tables(tmp_path):
    from app.db.session import create_db_engine

    db_path = tmp_path / "downgrade.db"
    url = f"sqlite:///{db_path}"
    config = alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_db_engine(url)
    try:
        with engine.connect() as connection:
            remaining = set(inspect(engine).get_table_names())
            assert "users" not in remaining
            assert "jobs" not in remaining
            revision = connection.execute(
                text("SELECT count(*) FROM sqlite_master WHERE name = 'alembic_version'")
            ).scalar_one()
            assert revision in {0, 1}
    finally:
        engine.dispose()


def test_foreign_keys_are_enforced(db, user1):
    """SQLite foreign keys must be ON, otherwise cascade deletes break."""
    value = db.execute(text("PRAGMA foreign_keys")).scalar_one()
    assert value == 1
