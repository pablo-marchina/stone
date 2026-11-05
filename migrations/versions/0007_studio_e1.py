"""IMP-177: versioned DesignDocument storage, static text-layer MVP only.

Revision ID: 0007_studio_e1
Revises: 0006_discovery_provenance
"""
from alembic import op
from sqlalchemy import (
    MetaData, Table, Column, String, Integer, Text, LargeBinary,
    ForeignKeyConstraint, inspect,
)
from sqlalchemy.schema import CreateTable, DropTable

revision = "0007_studio_e1"
down_revision = "0006_discovery_provenance"
branch_labels = None
depends_on = None


def _tables():
    frozen = MetaData()
    Table("tenants", frozen, Column("tenant_id", String(128), primary_key=True))
    documents = Table(
        "studio_documents", frozen,
        Column("tenant_id", String(128), primary_key=True),
        Column("document_id", String(128), primary_key=True),
        Column("spec_id", String(128), nullable=False),
        Column("current_version", Integer, nullable=False),
        ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
    )
    versions = Table(
        "studio_document_versions", frozen,
        Column("tenant_id", String(128), primary_key=True),
        Column("document_id", String(128), primary_key=True),
        Column("version", Integer, primary_key=True),
        Column("payload", Text, nullable=False),
        Column("created_at", String(48), nullable=False),
        Column("edited_by", String(128), nullable=False),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["studio_documents.tenant_id", "studio_documents.document_id"],
        ),
    )
    assets = Table(
        "studio_assets", frozen,
        Column("tenant_id", String(128), primary_key=True),
        Column("asset_id", String(128), primary_key=True),
        Column("sha256", String(64), nullable=False),
        Column("media_type", String(32), nullable=False),
        Column("byte_size", Integer, nullable=False),
        Column("width", Integer, nullable=False),
        Column("height", Integer, nullable=False),
        Column("rights_status", String(32), nullable=False),
        Column("uploaded_at", String(48), nullable=False),
        Column("uploaded_by", String(128), nullable=False),
        Column("data", LargeBinary, nullable=False),
        ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
    )
    return documents, versions, assets


def upgrade():
    connection = op.get_bind()
    docs, versions, assets = _tables()
    for table in (docs, versions, assets):
        if inspect(connection).has_table(table.name):
            raise RuntimeError("STUDIO_TABLE_ALREADY_EXISTS_OUTSIDE_ALEMBIC")
        connection.execute(CreateTable(table))


def downgrade():
    connection = op.get_bind()
    docs, versions, assets = _tables()
    connection.execute(DropTable(assets))
    connection.execute(DropTable(versions))
    connection.execute(DropTable(docs))
