"""Original official metadata ingestion schema, frozen at revision 0002.

Revision ID: 0002_official_ingestion
Revises: 0001_identity_domain_outbox

Do not import live ingestion Table objects into this historical migration:
newer revisions must be able to add fields and tables independently.
"""
from alembic import op
from sqlalchemy import (MetaData, Table, Column, String, Integer,
                        ForeignKeyConstraint, inspect)
from sqlalchemy.schema import CreateTable, DropTable

revision = "0002_official_ingestion"
down_revision = "0001_identity_domain_outbox"
branch_labels = None
depends_on = None


def _tables():
    frozen = MetaData()
    # FK destinations are already created by revision 0001. Minimal local
    # declarations allow SQLAlchemy to compile composite foreign keys.
    Table("tenants", frozen, Column("tenant_id", String(128), primary_key=True))
    Table("content_items", frozen,
          Column("tenant_id", String(128), primary_key=True),
          Column("id", String(128), primary_key=True))
    grants = Table("ingestion_source_grants", frozen,
        Column("tenant_id", String(128), primary_key=True),
        Column("platform", String(32), primary_key=True),
        Column("source_account_id", String(128), primary_key=True),
        Column("approval_reference", String(512), nullable=False),
        Column("approved_by", String(128), nullable=False),
        Column("approved_at", String(40), nullable=False),
        Column("expires_at", String(40), nullable=False),
        Column("technical_verified_at", String(40)),
        Column("enabled", Integer, nullable=False, default=1),
        ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]))
    runs = Table("ingestion_runs", frozen,
        Column("tenant_id", String(128), primary_key=True),
        Column("run_key", String(128), primary_key=True),
        Column("platform", String(32), nullable=False),
        Column("source_account_id", String(128), nullable=False),
        Column("requested_at", String(40), nullable=False),
        Column("status", String(24), nullable=False),
        Column("new_records", Integer, nullable=False, default=0),
        Column("duplicate_records", Integer, nullable=False, default=0),
        Column("reason_code", String(80)),
        ForeignKeyConstraint(["tenant_id", "platform", "source_account_id"],
            ["ingestion_source_grants.tenant_id",
             "ingestion_source_grants.platform",
             "ingestion_source_grants.source_account_id"]))
    records = Table("ingestion_records", frozen,
        Column("tenant_id", String(128), primary_key=True),
        Column("platform", String(32), primary_key=True),
        Column("source_account_id", String(128), primary_key=True),
        Column("source_item_id", String(128), primary_key=True),
        Column("content_id", String(128), nullable=False),
        Column("denominator_quality", String(40), nullable=False),
        Column("metadata_only", Integer, nullable=False),
        Column("processed_at", String(40), nullable=False),
        ForeignKeyConstraint(["tenant_id", "content_id"],
                             ["content_items.tenant_id", "content_items.id"]),
        ForeignKeyConstraint(["tenant_id", "platform", "source_account_id"],
            ["ingestion_source_grants.tenant_id",
             "ingestion_source_grants.platform",
             "ingestion_source_grants.source_account_id"]))
    return grants, runs, records


def upgrade():
    conn = op.get_bind()
    for table in _tables():
        if inspect(conn).has_table(table.name):
            raise RuntimeError("ingestion migration already applied outside Alembic")
        conn.execute(CreateTable(table))


def downgrade():
    conn = op.get_bind()
    for table in reversed(_tables()):
        conn.execute(DropTable(table))
