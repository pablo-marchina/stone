"""A02.5 durable job reservations and attempts; empty by default."""
from alembic import op
import sqlalchemy as sa

revision="0015_asset_jobs"
down_revision="0014_asset_lineage"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("asset_processing_jobs",
        sa.Column("tenant_id",sa.String(128),primary_key=True),sa.Column("job_id",sa.String(128),primary_key=True),
        sa.Column("object_id",sa.String(64),nullable=False),sa.Column("spec",sa.Text(),nullable=False),
        sa.Column("state",sa.String(24),nullable=False),sa.Column("attempt",sa.Integer(),nullable=False),
        sa.Column("version",sa.Integer(),nullable=False),sa.Column("created_ms",sa.BigInteger(),nullable=False),
        sa.Column("updated_ms",sa.BigInteger(),nullable=False),sa.Column("available_ms",sa.BigInteger(),nullable=False),
        sa.Column("worker",sa.String(128)),sa.Column("fence",sa.String(32)),sa.Column("lease_ms",sa.BigInteger()),
        sa.Column("deadline_ms",sa.BigInteger()),sa.Column("receipt_sha256",sa.String(64)),sa.Column("reason",sa.String(64)),
        sa.ForeignKeyConstraint(["tenant_id","object_id"],["asset_lineage_nodes.tenant_id","asset_lineage_nodes.node_id"]),
        sa.CheckConstraint("state IN ('queued','running','cancel_requested','completed','failed','canceled')",name="ck_asset_job_state"),
        sa.CheckConstraint("attempt BETWEEN 0 AND 3 AND version>=1",name="ck_asset_job_attempt"),
        sa.CheckConstraint("(state IN ('running','cancel_requested') AND worker IS NOT NULL AND fence IS NOT NULL AND lease_ms IS NOT NULL AND deadline_ms IS NOT NULL AND lease_ms<=deadline_ms) OR (state NOT IN ('running','cancel_requested') AND worker IS NULL AND fence IS NULL AND lease_ms IS NULL AND deadline_ms IS NULL)",name="ck_asset_job_lease"),
        sa.CheckConstraint("(state='completed' AND receipt_sha256 IS NOT NULL) OR (state!='completed' AND receipt_sha256 IS NULL)",name="ck_asset_job_receipt"))
    op.create_index("ix_asset_job_dispatch","asset_processing_jobs",["tenant_id","state","available_ms","job_id"])
    op.create_table("asset_processing_attempts",
        sa.Column("tenant_id",sa.String(128),primary_key=True),sa.Column("job_id",sa.String(128),primary_key=True),
        sa.Column("attempt",sa.Integer(),primary_key=True),sa.Column("started_ms",sa.BigInteger(),nullable=False),
        sa.ForeignKeyConstraint(["tenant_id","job_id"],["asset_processing_jobs.tenant_id","asset_processing_jobs.job_id"]),
        sa.CheckConstraint("attempt BETWEEN 1 AND 3",name="ck_asset_attempt_number"))
    op.create_index("ix_asset_attempt_budget","asset_processing_attempts",["started_ms","tenant_id"])


def downgrade():
    bind=op.get_bind()
    for name in ("asset_processing_attempts","asset_processing_jobs"):
        if bind.execute(sa.text("SELECT count(*) FROM "+name)).scalar_one():
            raise RuntimeError("ASSET_JOBS_DOWNGRADE_NONEMPTY")
    op.drop_table("asset_processing_attempts")
    op.drop_table("asset_processing_jobs")
