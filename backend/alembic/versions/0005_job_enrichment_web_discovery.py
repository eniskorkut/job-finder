"""job enrichment, web discovery, and freshness tracking

Revision ID: 0005_job_enrichment_web_discovery
Revises: 0004_durable_retry_delay
Create Date: 2026-09-29 08:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_job_enrichment_web_discovery'
down_revision: Union[str, Sequence[str], None] = '0004_durable_retry_delay'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'job_web_sources',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('normalized_url', sa.Text(), nullable=False),
        sa.Column('host', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=30), nullable=False),
        sa.Column('trust_level', sa.Integer(), server_default='0', nullable=False),
        sa.Column('match_confidence', sa.String(length=20), server_default='none', nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('snippet', sa.Text(), nullable=True),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('selected_as_canonical', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('discovered_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_job_web_sources_job_id_jobs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_job_web_sources_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_job_web_sources')),
        sa.UniqueConstraint('job_id', 'normalized_url', name='uq_job_web_sources_job_normalized_url')
    )
    with op.batch_alter_table('job_web_sources', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_job_web_sources_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_job_web_sources_user_id'), ['user_id'], unique=False)

    op.create_table(
        'enrichment_items',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('sync_job_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='queued', nullable=False),
        sa.Column('attempt', sa.Integer(), server_default='0', nullable=False),
        sa.Column('source_type', sa.String(length=30), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('error_class', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_enrichment_items_job_id_jobs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sync_job_id'], ['sync_jobs.id'], name=op.f('fk_enrichment_items_sync_job_id_sync_jobs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_enrichment_items_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_enrichment_items')),
        sa.UniqueConstraint('sync_job_id', 'job_id', name='uq_enrichment_items_job_entry')
    )
    with op.batch_alter_table('enrichment_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_enrichment_items_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_enrichment_items_sync_job_id'), ['sync_job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_enrichment_items_user_id'), ['user_id'], unique=False)
        batch_op.create_index('ix_enrichment_items_user_status', ['user_id', 'status'], unique=False)

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('linkedin_url', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('company_job_url', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('canonical_url', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('application_url', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('source_url', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('email_received_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('valid_through', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('last_enriched_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('posted_at_source', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('posted_at_confidence', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('freshness_status', sa.String(length=20), server_default='fresh', nullable=False))
        batch_op.add_column(sa.Column('availability_status', sa.String(length=20), server_default='unknown', nullable=False))
        batch_op.add_column(sa.Column('enrichment_status', sa.String(length=30), server_default='pending', nullable=False))
        batch_op.add_column(sa.Column('content_hash', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_jobs_content_hash'), ['content_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_enrichment_status'), ['enrichment_status'], unique=False)
        batch_op.create_index(batch_op.f('ix_jobs_freshness_status'), ['freshness_status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_jobs_freshness_status'))
        batch_op.drop_index(batch_op.f('ix_jobs_enrichment_status'))
        batch_op.drop_index(batch_op.f('ix_jobs_content_hash'))
        batch_op.drop_column('content_hash')
        batch_op.drop_column('enrichment_status')
        batch_op.drop_column('availability_status')
        batch_op.drop_column('freshness_status')
        batch_op.drop_column('posted_at_confidence')
        batch_op.drop_column('posted_at_source')
        batch_op.drop_column('last_enriched_at')
        batch_op.drop_column('last_verified_at')
        batch_op.drop_column('valid_through')
        batch_op.drop_column('email_received_at')
        batch_op.drop_column('source_url')
        batch_op.drop_column('application_url')
        batch_op.drop_column('canonical_url')
        batch_op.drop_column('company_job_url')
        batch_op.drop_column('linkedin_url')

    with op.batch_alter_table('enrichment_items', schema=None) as batch_op:
        batch_op.drop_index('ix_enrichment_items_user_status')
        batch_op.drop_index(batch_op.f('ix_enrichment_items_user_id'))
        batch_op.drop_index(batch_op.f('ix_enrichment_items_sync_job_id'))
        batch_op.drop_index(batch_op.f('ix_enrichment_items_job_id'))

    op.drop_table('enrichment_items')

    with op.batch_alter_table('job_web_sources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_web_sources_user_id'))
        batch_op.drop_index(batch_op.f('ix_job_web_sources_job_id'))

    op.drop_table('job_web_sources')
