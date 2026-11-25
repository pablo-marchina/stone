"""A02.4 private lineage metadata, empty by default."""
from alembic import op
import sqlalchemy as sa

revision="0014_asset_lineage"
down_revision="0013_asset_rights_registry"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("asset_lineage_nodes",
        sa.Column("tenant_id",sa.String(128),primary_key=True),
        sa.Column("node_id",sa.String(128),primary_key=True),
        sa.Column("kind",sa.String(32),nullable=False),
        sa.Column("payload",sa.Text(),nullable=False),
        sa.Column("purpose",sa.String(32),nullable=False),
        sa.Column("state",sa.String(16),nullable=False),
        sa.Column("invalidated_at",sa.String(40)),
        sa.ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"]),
        sa.CheckConstraint("kind IN ('asset','derived')",name="ck_lineage_kind"),
        sa.CheckConstraint("purpose IN ('research_analysis','studio_creation')",name="ck_lineage_purpose"),
        sa.CheckConstraint("(state='active' AND invalidated_at IS NULL) OR "
                           "(state='invalidated' AND invalidated_at IS NOT NULL)",name="ck_lineage_state"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM asset_lineage_nodes")).scalar_one():
        raise RuntimeError("ASSET_LINEAGE_DOWNGRADE_NONEMPTY")
    op.drop_table("asset_lineage_nodes")
