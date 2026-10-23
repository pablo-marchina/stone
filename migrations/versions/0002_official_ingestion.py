"""Official-source metadata grants, run ledger, and normalized-record links.

Revision ID: 0002_official_ingestion
Revises: 0001_identity_domain_outbox
"""
from alembic import op
from sqlalchemy.schema import CreateTable, CreateIndex, DropTable
from sqlalchemy import inspect

revision="0002_official_ingestion"
down_revision="0001_identity_domain_outbox"
branch_labels=None
depends_on=None


def _tables():
    # Import only when migration 0002 executes: prevent 0001 metadata pollution.
    from tapi_gate0.ingestion import source_grants, ingestion_runs, ingestion_records
    return source_grants,ingestion_runs,ingestion_records


def upgrade():
    conn=op.get_bind()
    for table in _tables():
        if inspect(conn).has_table(table.name):
            raise RuntimeError("ingestion migration already applied outside Alembic")
        conn.execute(CreateTable(table))
        for index in table.indexes:conn.execute(CreateIndex(index))


def downgrade():
    conn=op.get_bind()
    for table in reversed(_tables()):conn.execute(DropTable(table))
