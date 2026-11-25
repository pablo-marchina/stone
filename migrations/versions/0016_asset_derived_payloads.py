"""A02 encrypted derived payloads; empty by default."""
from alembic import op
import sqlalchemy as sa

revision="0016_asset_derived_payloads"
down_revision="0015_asset_jobs"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("asset_derived_payloads",
        sa.Column("tenant_id",sa.String(128),primary_key=True),
        sa.Column("artifact_id",sa.String(128),primary_key=True),
        sa.Column("job_id",sa.String(128),nullable=False),
        sa.Column("key_id",sa.String(64),nullable=False),
        sa.Column("byte_count",sa.Integer(),nullable=False),
        sa.Column("attempt",sa.Integer(),nullable=False),
        sa.Column("envelope",sa.LargeBinary()),
        sa.Column("purged_at",sa.String(40)),
        sa.ForeignKeyConstraint(["tenant_id","artifact_id"],["asset_lineage_nodes.tenant_id","asset_lineage_nodes.node_id"]),
        sa.ForeignKeyConstraint(["tenant_id","job_id"],["asset_processing_jobs.tenant_id","asset_processing_jobs.job_id"]),
        sa.UniqueConstraint("tenant_id","job_id",name="uq_asset_payload_job"),
        sa.CheckConstraint("byte_count BETWEEN 1 AND 1000000 AND attempt BETWEEN 1 AND 3",name="ck_asset_payload_bounds"),
        sa.CheckConstraint("(envelope IS NOT NULL AND purged_at IS NULL AND length(envelope)=byte_count+28) OR (envelope IS NULL AND purged_at IS NOT NULL)",name="ck_asset_payload_state"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM asset_derived_payloads")).scalar_one():
        raise RuntimeError("ASSET_PAYLOAD_DOWNGRADE_NONEMPTY")
    op.drop_table("asset_derived_payloads")
