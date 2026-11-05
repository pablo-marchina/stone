"""CAP-023 E6: auditable rights, local rendering, and evidence edit events.

Revision ID: 0009_studio_local_render_e6
Revises: 0008_studio_storyboards
"""
from alembic import op
import sqlalchemy as sa

revision='0009_studio_local_render_e6'
down_revision='0008_studio_storyboards'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('studio_render_rights',
        sa.Column('tenant_id',sa.String(128),primary_key=True),
        sa.Column('asset_id',sa.String(128),primary_key=True),
        sa.Column('kind',sa.String(12),nullable=False),
        sa.Column('content_sha256',sa.String(64),nullable=False),
        sa.Column('evidence_reference',sa.String(512),nullable=False),
        sa.Column('expires_at',sa.String(48),nullable=False),
        sa.Column('status',sa.String(12),nullable=False),
        sa.Column('attested_by',sa.String(128),nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'],['tenants.tenant_id']))
    op.create_table('studio_render_rights_events',
        sa.Column('event_id',sa.String(36),primary_key=True),
        sa.Column('tenant_id',sa.String(128),nullable=False),
        sa.Column('asset_id',sa.String(128),nullable=False),
        sa.Column('action',sa.String(16),nullable=False),
        sa.Column('actor',sa.String(128),nullable=False),
        sa.Column('at',sa.String(48),nullable=False),
        sa.Column('evidence_reference',sa.String(512)),
        sa.Column('content_sha256',sa.String(64)),
        sa.ForeignKeyConstraint(['tenant_id','asset_id'],
            ['studio_render_rights.tenant_id','studio_render_rights.asset_id']))
    op.create_table('studio_render_audio',
        sa.Column('tenant_id',sa.String(128),primary_key=True),
        sa.Column('asset_id',sa.String(128),primary_key=True),
        sa.Column('content_sha256',sa.String(64),nullable=False),
        sa.Column('duration_ms',sa.Integer,nullable=False),
        sa.Column('data',sa.LargeBinary,nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'],['tenants.tenant_id']))
    op.create_table('studio_render_jobs',
        sa.Column('tenant_id',sa.String(128),primary_key=True),
        sa.Column('job_id',sa.String(128),primary_key=True),
        sa.Column('storyboard_id',sa.String(128),nullable=False),
        sa.Column('storyboard_version',sa.Integer,nullable=False),
        sa.Column('status',sa.String(12),nullable=False),
        sa.Column('attempts',sa.Integer,nullable=False),
        sa.Column('cancel_requested',sa.Integer,nullable=False),
        sa.Column('manifest',sa.Text,nullable=False),
        sa.Column('manifest_sha256',sa.String(64),nullable=False),
        sa.Column('artifact_id',sa.String(128)),
        sa.Column('error_code',sa.String(64)),
        sa.Column('created_by',sa.String(128),nullable=False),
        sa.Column('created_at',sa.String(48),nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'],['tenants.tenant_id']))
    op.create_table('studio_render_artifacts',
        sa.Column('tenant_id',sa.String(128),primary_key=True),
        sa.Column('artifact_id',sa.String(128),primary_key=True),
        sa.Column('job_id',sa.String(128),nullable=False),
        sa.Column('content_sha256',sa.String(64),nullable=False),
        sa.Column('byte_size',sa.Integer,nullable=False),
        sa.Column('duration_ms',sa.Integer,nullable=False),
        sa.Column('data',sa.LargeBinary,nullable=False),
        sa.ForeignKeyConstraint(['tenant_id','job_id'],
            ['studio_render_jobs.tenant_id','studio_render_jobs.job_id']))
    op.create_table('studio_render_events',
        sa.Column('event_id',sa.String(36),primary_key=True),
        sa.Column('tenant_id',sa.String(128),nullable=False),
        sa.Column('job_id',sa.String(128),nullable=False),
        sa.Column('action',sa.String(20),nullable=False),
        sa.Column('actor',sa.String(128),nullable=False),
        sa.Column('at',sa.String(48),nullable=False),
        sa.ForeignKeyConstraint(['tenant_id','job_id'],
            ['studio_render_jobs.tenant_id','studio_render_jobs.job_id']))
    op.create_table('studio_evidence_edit_events',
        sa.Column('event_id',sa.String(36),primary_key=True),
        sa.Column('tenant_id',sa.String(128),nullable=False),
        sa.Column('document_id',sa.String(128),nullable=False),
        sa.Column('document_version',sa.Integer,nullable=False),
        sa.Column('content_id',sa.String(128),nullable=False),
        sa.Column('snapshot_id',sa.String(128),nullable=False),
        sa.Column('snapshot_sha256',sa.String(64),nullable=False),
        sa.Column('preview_sha256',sa.String(64),nullable=False),
        sa.Column('operator_id',sa.String(128),nullable=False),
        sa.Column('created_at',sa.String(48),nullable=False),
        sa.ForeignKeyConstraint(['tenant_id','document_id','document_version'],
            ['studio_document_versions.tenant_id','studio_document_versions.document_id','studio_document_versions.version']))


def downgrade():
    for name in ['studio_evidence_edit_events','studio_render_events',
                 'studio_render_artifacts','studio_render_jobs','studio_render_audio',
                 'studio_render_rights_events','studio_render_rights']:
        op.drop_table(name)
