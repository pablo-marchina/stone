"""Initial unified domain, multi-tenant identity and transactional event outbox.

Revision ID: 0001_identity_domain_outbox
Revises:
"""
from alembic import op
from sqlalchemy.schema import CreateTable, CreateIndex, DropTable
from tapi_gate0.sa_store import metadata
from tapi_gate0 import identity  # noqa: F401, ensures identity table registration

revision="0001_identity_domain_outbox"
down_revision=None
branch_labels=None
depends_on=None


def upgrade():
    connection=op.get_bind()
    for table in metadata.sorted_tables:
        connection.execute(CreateTable(table))
    for table in metadata.sorted_tables:
        for index in table.indexes:
            connection.execute(CreateIndex(index))


def downgrade():
    connection=op.get_bind()
    for table in reversed(metadata.sorted_tables):
        connection.execute(DropTable(table))