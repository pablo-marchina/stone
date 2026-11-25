"""CAP-001 A5 private historical cursor and tenant cycle lease.

Revision ID: 0012_bd_history_checkpoints
Revises: 0011_studio_source_audio_hq_e8
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_bd_history_checkpoints"
down_revision = "0011_studio_source_audio_hq_e8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("bd_history_checkpoints",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("source_account_id", sa.String(128), primary_key=True),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("viewer_ig_id", sa.String(32), nullable=False),
        sa.Column("approval_reference", sa.String(512), nullable=False),
        sa.Column("next_cursor", sa.String(512)),
        sa.Column("cursor_hashes", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("pages_examined", sa.Integer, nullable=False),
        sa.Column("last_run_key", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "platform", "source_account_id"],
            ["ingestion_source_grants.tenant_id", "ingestion_source_grants.platform",
             "ingestion_source_grants.source_account_id"]))
    op.create_table("bd_cycle_leases",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("cycle_key", sa.String(80), nullable=False),
        sa.Column("started_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]))


def downgrade():
    op.drop_table("bd_cycle_leases")
    op.drop_table("bd_history_checkpoints")
