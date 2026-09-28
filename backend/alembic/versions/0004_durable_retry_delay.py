"""add next_attempt_at to sync_jobs for durable retry delay

Revision ID: 0004_durable_retry_delay
Revises: 0003_phase3_scoring_telegram_scheduler
Create Date: 2026-09-28 20:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004_durable_retry_delay'
down_revision: Union[str, Sequence[str], None] = '0003_phase3_scoring_telegram_scheduler'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('sync_jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_sync_jobs_next_attempt_at'), ['next_attempt_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('sync_jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sync_jobs_next_attempt_at'))
        batch_op.drop_column('next_attempt_at')
