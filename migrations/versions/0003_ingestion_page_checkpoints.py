"""Durable Instagram cursor checkpoint after committed authorized page.

Revision ID: 0003_ingestion_page_checkpoints
Revises: 0002_official_ingestion
"""
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable, DropTable

revision = "0003_ingestion_page_checkpoints"
down_revision = "0002_official_ingestion"
branch_labels = None
depends_on = None


def upgrade():
    # The existing 0002 migration defines only the three original ingestion
    # tables; keep checkpoint evolution isolated in a dedicated revision.
    from tapi_gate0.ingestion import ingestion_page_checkpoints
    conn = op.get_bind()
    if inspect(conn).has_table(ingestion_page_checkpoints.name):
        raise RuntimeError("checkpoint table already exists outside Alembic")
    conn.execute(CreateTable(ingestion_page_checkpoints))


def downgrade():
    from tapi_gate0.ingestion import ingestion_page_checkpoints
    op.get_bind().execute(DropTable(ingestion_page_checkpoints))
