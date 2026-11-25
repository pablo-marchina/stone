"""A05.4 signed creative-reference registry schema, EMPTY and OFF by default.

The operational PEP uses these tables only when a host independently injects
trusted reference authorities. This migration does not provision keys, approvals,
grants, data, endpoint permissions, billing or production readiness.

Revision ID: 0017_creative_reference_pep
Revises: 0016_asset_derived_payloads
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_creative_reference_pep"
down_revision = "0016_asset_derived_payloads"
branch_labels = None
depends_on = None


def _keys():
    return (
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("platform", sa.String(32), primary_key=True),
        sa.Column("issuer_id", sa.String(128), primary_key=True),
    )


def _authority_fk():
    return sa.ForeignKeyConstraint(
        ["tenant_id", "platform", "issuer_id"],
        ["a054_reference_authorities.tenant_id",
         "a054_reference_authorities.platform",
         "a054_reference_authorities.issuer_id"],
    )


def upgrade():
    op.create_table(
        "a054_reference_authorities", *_keys(),
        sa.Column("public_key_sha256", sa.String(64), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("state_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
    )
    op.create_table(
        "a054_reference_revocations", *_keys(),
        sa.Column("revision", sa.BigInteger(), primary_key=True),
        sa.Column("state_sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        _authority_fk(),
    )
    op.create_table(
        "a054_reference_grants", *_keys(),
        sa.Column("grant_id", sa.String(128), primary_key=True),
        sa.Column("content_id", sa.String(128), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("claims_sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        _authority_fk(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "content_id"],
            ["content_items.tenant_id", "content_items.id"],
        ),
    )


def downgrade():
    # Never silently erase an independently signed grant/revocation history.
    # Populated rollback requires a separately reviewed recovery procedure.
    db = op.get_bind()
    tables = (
        "a054_reference_grants",
        "a054_reference_revocations",
        "a054_reference_authorities",
    )
    for table in tables:
        if db.execute(sa.text("SELECT count(*) FROM " + table)).scalar_one():
            raise RuntimeError("CREATIVE_REF_REGISTRY_DOWNGRADE_NONEMPTY")
    for table in tables:
        op.drop_table(table)
