"""CAP-023 exact external reference grant binding, empty by default.

Revision ID: 0018_studio_reference_bindings
Revises: 0017_creative_reference_pep
No backfill, no rights change, no automatic approval or deployment.
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_studio_reference_bindings"
down_revision = "0017_creative_reference_pep"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "studio_reference_bindings",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("document_id", sa.String(128), primary_key=True),
        sa.Column("content_id", sa.String(128), primary_key=True),
        sa.Column("grant_id", sa.String(128), nullable=False),
        sa.Column("reference_set_sha256", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.String(48), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["studio_documents.tenant_id", "studio_documents.document_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "content_id"],
            ["content_items.tenant_id", "content_items.id"],
            ondelete="RESTRICT",
        ),
    )


def downgrade():
    db = op.get_bind()
    if db.execute(sa.text(
            "SELECT count(*) FROM studio_reference_bindings")).scalar_one():
        raise RuntimeError("STUDIO_REFERENCE_BINDINGS_DOWNGRADE_NONEMPTY")
    op.drop_table("studio_reference_bindings")
