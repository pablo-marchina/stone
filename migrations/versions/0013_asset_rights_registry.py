"""A02.2 signed rights registry, empty by default.
Revision ID: 0013_asset_rights_registry
Revises: 0012_bd_history_checkpoints
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_asset_rights_registry"
down_revision = "0012_bd_history_checkpoints"
branch_labels = None
depends_on = None


def keys():
    return [sa.Column("tenant_id",sa.String(128),primary_key=True),
            sa.Column("platform",sa.String(32),primary_key=True),
            sa.Column("issuer_id",sa.String(128),primary_key=True)]


def authority_fk():
    return sa.ForeignKeyConstraint(["tenant_id","platform","issuer_id"],
        ["asset_rights_authorities.tenant_id","asset_rights_authorities.platform",
         "asset_rights_authorities.issuer_id"])


def upgrade():
    op.create_table("asset_rights_authorities",*keys(),
        sa.Column("key_sha256",sa.String(64),nullable=False),
        sa.Column("revision",sa.BigInteger(),nullable=False),
        sa.Column("claims_sha256",sa.String(64),nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"],["tenants.tenant_id"]))
    op.create_table("asset_rights_revocations",*keys(),
        sa.Column("revision",sa.BigInteger(),primary_key=True),
        sa.Column("claims_sha256",sa.String(64),nullable=False),
        sa.Column("payload",sa.Text(),nullable=False),authority_fk())
    op.create_table("asset_rights_grants",*keys(),
        sa.Column("grant_id",sa.String(128),primary_key=True),
        sa.Column("content_id",sa.String(128),nullable=False),
        sa.Column("asset_id",sa.String(128),nullable=False),
        sa.Column("claims_sha256",sa.String(64),nullable=False),
        sa.Column("payload",sa.Text(),nullable=False),authority_fk(),
        sa.ForeignKeyConstraint(["tenant_id","content_id"],["content_items.tenant_id","content_items.id"]))


def downgrade():
    # Never silently discard revocation history. A rollback of a populated
    # rights registry requires a separately reviewed recovery procedure.
    bind=op.get_bind()
    for table in ("asset_rights_grants","asset_rights_revocations","asset_rights_authorities"):
        if bind.execute(sa.text("SELECT count(*) FROM "+table)).scalar_one():
            raise RuntimeError("ASSET_REGISTRY_DOWNGRADE_NONEMPTY")
    op.drop_table("asset_rights_grants")
    op.drop_table("asset_rights_revocations")
    op.drop_table("asset_rights_authorities")
