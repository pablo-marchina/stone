"""Durable Instagram cursor checkpoints and metric refresh run counters.

Revision ID: 0003_ingestion_page_checkpoints
Revises: 0002_official_ingestion
"""
from alembic import op
from sqlalchemy import Column, Integer, inspect
from sqlalchemy.schema import CreateTable, DropTable

revision = "0003_ingestion_page_checkpoints"
down_revision = "0002_official_ingestion"
branch_labels = None
depends_on = None


def upgrade():
    from tapi_gate0.ingestion import ingestion_page_checkpoints
    conn = op.get_bind()
    if inspect(conn).has_table(ingestion_page_checkpoints.name):
        raise RuntimeError("checkpoint table already exists outside Alembic")
    conn.execute(CreateTable(ingestion_page_checkpoints))
    # 0002 uses live table declarations. On fresh database installations,
    # that revision may already contain the new counter; on older databases,
    # 0003 must introduce it. Both paths must produce the same schema.
    columns = {c["name"] for c in inspect(conn).get_columns("ingestion_runs")}
    if "refreshed_records" not in columns:
        op.add_column("ingestion_runs", Column(
            "refreshed_records", Integer, nullable=False, server_default="0"))


def downgrade():
    from tapi_gate0.ingestion import ingestion_page_checkpoints
    op.drop_column("ingestion_runs", "refreshed_records")
    op.get_bind().execute(DropTable(ingestion_page_checkpoints))
