"""Initial unified domain, identity, and transactional event outbox.

Revision ID: 0001_identity_domain_outbox
Revises:

Historical Alembic revisions must not depend on what tables newer modules
register in the shared metadata at import time.
"""
from alembic import op
from sqlalchemy.schema import CreateTable, CreateIndex, DropTable
from tapi_gate0.sa_store import metadata
from tapi_gate0 import identity  # noqa: F401, ensures baseline identity registration

revision = "0001_identity_domain_outbox"
down_revision = None
branch_labels = None
depends_on = None

# Deliberately frozen to the tables introduced by revision 0001. Other tables
# are created only by their own migrations, regardless of import order.
BASELINE_TABLE_NAMES = frozenset({
    "tenants", "creators", "content_items", "metrics_snapshots",
    "rubric_assessments", "insights", "creative_versions", "domain_events",
    "event_outbox", "identity_users", "identity_memberships",
    "identity_sessions", "identity_audit",
})


def _tables():
    tables = [t for t in metadata.sorted_tables if t.name in BASELINE_TABLE_NAMES]
    if {t.name for t in tables} != BASELINE_TABLE_NAMES:
        raise RuntimeError("baseline 0001 table definitions are incomplete")
    return tables


def upgrade():
    conn = op.get_bind()
    for table in _tables():
        conn.execute(CreateTable(table))
    for table in _tables():
        for index in table.indexes:
            conn.execute(CreateIndex(index))


def downgrade():
    conn = op.get_bind()
    for table in reversed(_tables()):
        conn.execute(DropTable(table))
