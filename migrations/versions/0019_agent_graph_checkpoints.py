"""IMP-074 / CAP-005: private agent graph trace checkpoints, zero grants.

Revision ID: 0019_agent_graph_checkpoints
Revises: 0018_studio_reference_bindings
No backfill, no external tool execution, no model calls or rights changes.
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_agent_graph_checkpoints"
down_revision = "0018_studio_reference_bindings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_graph_runs",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("actor_sha256", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("cursor", sa.String(40)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("chain_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(48), nullable=False),
        sa.Column("updated_at", sa.String(48), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"],
                                ondelete="RESTRICT"),
    )
    op.create_table(
        "agent_graph_events",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("sequence", sa.Integer, primary_key=True),
        sa.Column("node", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.Column("chain_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(48), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "run_id"],
                                ["agent_graph_runs.tenant_id", "agent_graph_runs.run_id"],
                                ondelete="RESTRICT"),
    )


def downgrade():
    db = op.get_bind()
    for table in ("agent_graph_events", "agent_graph_runs"):
        if db.execute(sa.text("SELECT count(*) FROM " + table)).scalar_one():
            raise RuntimeError("AGENT_GRAPH_CHECKPOINT_DOWNGRADE_NONEMPTY")
    op.drop_table("agent_graph_events")
    op.drop_table("agent_graph_runs")
