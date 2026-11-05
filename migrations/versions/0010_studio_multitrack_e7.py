"""CAP-023 E7: source-bound video, resilient render jobs and audit.

Revision ID: 0010_studio_multitrack_e7
Revises: 0009_studio_local_render_e6
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_studio_multitrack_e7"
down_revision = "0009_studio_local_render_e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("studio_e7_video_sources",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("asset_id", sa.String(128), primary_key=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.String(48), nullable=False),
        sa.Column("rights_status", sa.String(16), nullable=False),
        sa.Column("evidence_reference", sa.String(512), nullable=False),
        sa.Column("attested_by", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"]))
    op.create_table("studio_e7_render_jobs",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("job_id", sa.String(128), primary_key=True),
        sa.Column("storyboard_id", sa.String(128), nullable=False),
        sa.Column("storyboard_version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.String(48)),
        sa.Column("manifest", sa.Text, nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("artifact_id", sa.String(128)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.String(48), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"]))
    op.create_table("studio_e7_render_artifacts",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("artifact_id", sa.String(128), primary_key=True),
        sa.Column("job_id", sa.String(128), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.ForeignKeyConstraint(["tenant_id","job_id"],
            ["studio_e7_render_jobs.tenant_id","studio_e7_render_jobs.job_id"]))
    op.create_table("studio_e7_render_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("job_id", sa.String(128)),
        sa.Column("asset_id", sa.String(128)),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.String(48), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"]))
    op.create_index("ix_e7_jobs_pending", "studio_e7_render_jobs",
                    ["tenant_id", "status", "created_at"])


def downgrade():
    op.drop_index("ix_e7_jobs_pending",table_name="studio_e7_render_jobs")
    for table in ("studio_e7_render_events","studio_e7_render_artifacts",
                  "studio_e7_render_jobs","studio_e7_video_sources"):
        op.drop_table(table)
