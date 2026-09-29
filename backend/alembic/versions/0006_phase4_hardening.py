"""phase 4 hardening: freshness default unknown, etag, last_modified, job_content_hash

Revision ID: 0006_phase4_hardening
Revises: 0005_job_enrichment_web_discovery
Create Date: 2026-09-29 18:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_phase4_hardening'
down_revision: Union[str, Sequence[str], None] = '0005_job_enrichment_web_discovery'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('job_web_sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('etag', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('last_modified', sa.String(length=100), nullable=True))

    with op.batch_alter_table('job_matches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('job_content_hash', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_job_matches_job_content_hash'), ['job_content_hash'], unique=False)

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.alter_column(
            'freshness_status',
            existing_type=sa.String(length=20),
            server_default='unknown',
            nullable=False
        )

    # Backfill any nulls or empty freshness status
    op.execute(
        "UPDATE jobs SET freshness_status = 'unknown' WHERE freshness_status IS NULL OR freshness_status = ''"
    )


def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.alter_column(
            'freshness_status',
            existing_type=sa.String(length=20),
            server_default='fresh',
            nullable=False
        )

    with op.batch_alter_table('job_matches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_matches_job_content_hash'))
        batch_op.drop_column('job_content_hash')

    with op.batch_alter_table('job_web_sources', schema=None) as batch_op:
        batch_op.drop_column('last_modified')
        batch_op.drop_column('etag')
