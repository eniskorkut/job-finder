"""legacy freshness backfill and runtime hardening

Revision ID: 0007_legacy_freshness_and_runtime_hardening
Revises: 0006_phase4_hardening
Create Date: 2026-09-30 08:45:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007_legacy_freshness_and_runtime_hardening'
down_revision: Union[str, Sequence[str], None] = '0006_phase4_hardening'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Safely backfill legacy postings that were automatically set to 'fresh' during migration 0005
    # without having undergone enrichment or date verification.
    op.execute(
        """
        UPDATE jobs
        SET freshness_status = 'unknown'
        WHERE freshness_status = 'fresh'
          AND last_enriched_at IS NULL
          AND posted_at_source IS NULL
          AND last_verified_at IS NULL
        """
    )


def downgrade() -> None:
    # Reverting backfill: no structural schema changes to revert
    pass
