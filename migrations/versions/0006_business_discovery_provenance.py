"""Append-only third-party Business Discovery acquisition provenance.

Revision ID: 0006_discovery_provenance
Revises: 0005_scientific_corpus
"""
from alembic import op
from sqlalchemy import (MetaData, Table, Column, String, ForeignKeyConstraint, inspect)
from sqlalchemy.schema import CreateTable, DropTable

revision = "0006_discovery_provenance"
down_revision = "0005_scientific_corpus"
branch_labels = None
depends_on = None


def _table():
    frozen = MetaData()
    Table("ingestion_runs", frozen,
          Column("tenant_id", String(128), primary_key=True),
          Column("run_key", String(128), primary_key=True))
    Table("content_items", frozen,
          Column("tenant_id", String(128), primary_key=True),
          Column("id", String(128), primary_key=True))
    Table("ingestion_records", frozen,
          Column("tenant_id", String(128), primary_key=True),
          Column("platform", String(32), primary_key=True),
          Column("source_account_id", String(128), primary_key=True),
          Column("source_item_id", String(128), primary_key=True))
    return Table("business_discovery_provenance", frozen,
        Column("tenant_id", String(128), primary_key=True),
        Column("run_key", String(128), primary_key=True),
        Column("source_item_id", String(128), primary_key=True),
        Column("platform", String(32), nullable=False),
        Column("source_account_id", String(128), nullable=False),
        Column("content_id", String(128), nullable=False),
        Column("media_integrity_sha256", String(64), nullable=False),
        Column("batch_metadata_sha256", String(64), nullable=False),
        Column("approval_proof_sha256", String(64), nullable=False),
        Column("approval_reference", String(512), nullable=False),
        Column("acquisition_method", String(40), nullable=False),
        Column("graph_api_version", String(20), nullable=False),
        Column("observed_at", String(40), nullable=False),
        Column("recorded_at", String(40), nullable=False),
        ForeignKeyConstraint(["tenant_id", "run_key"],
                             ["ingestion_runs.tenant_id", "ingestion_runs.run_key"]),
        ForeignKeyConstraint(["tenant_id", "content_id"],
                             ["content_items.tenant_id", "content_items.id"]),
        ForeignKeyConstraint(["tenant_id", "platform", "source_account_id", "source_item_id"],
                             ["ingestion_records.tenant_id", "ingestion_records.platform",
                              "ingestion_records.source_account_id", "ingestion_records.source_item_id"]),
    )


def upgrade():
    connection = op.get_bind()
    table = _table()
    if inspect(connection).has_table(table.name):
        raise RuntimeError("provenance table already exists outside Alembic")
    connection.execute(CreateTable(table))


def downgrade():
    op.get_bind().execute(DropTable(_table()))
