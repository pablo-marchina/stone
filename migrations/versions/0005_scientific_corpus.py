"""Scientific source context and per-post audit decisions (DEC-016).

Revision ID: 0005_scientific_corpus
Revises: 0004_corpus_profiles

Historical tables are frozen: do not import changing live metadata here.
The unrelated draft PR #20 also proposed a revision 0005; it must be
rebased and renumbered before it can be integrated.
"""
from alembic import op
from sqlalchemy import (MetaData, Table, Column, String,
                        ForeignKeyConstraint, inspect)
from sqlalchemy.schema import CreateTable, DropTable

revision = "0005_scientific_corpus"
down_revision = "0004_corpus_profiles"
branch_labels = None
depends_on = None


def _tables():
    md = MetaData()
    Table("corpus_profiles", md,
          Column("tenant_id", String(128), primary_key=True),
          Column("platform", String(32), primary_key=True),
          Column("source_account_id", String(128), primary_key=True))
    Table("content_items", md,
          Column("tenant_id", String(128), primary_key=True),
          Column("id", String(128), primary_key=True))
    sources = Table("corpus_source_research_contexts", md,
        Column("tenant_id", String(128), primary_key=True),
        Column("platform", String(32), primary_key=True),
        Column("source_account_id", String(128), primary_key=True),
        Column("creator_type", String(40), nullable=False),
        Column("business_size_class", String(24), nullable=False),
        Column("business_size_evidence_reference", String(512)),
        Column("sector_context", String(32), nullable=False),
        Column("audience_intent", String(24), nullable=False),
        Column("audience_rationale_reference", String(512), nullable=False),
        Column("reviewed_by", String(128), nullable=False),
        Column("reviewed_at", String(40), nullable=False),
        ForeignKeyConstraint(["tenant_id","platform","source_account_id"],
                             ["corpus_profiles.tenant_id","corpus_profiles.platform",
                              "corpus_profiles.source_account_id"]),
    )
    posts = Table("corpus_post_scientific_reviews", md,
        Column("tenant_id", String(128), primary_key=True),
        Column("content_id", String(128), primary_key=True),
        Column("review_id", String(64), primary_key=True),
        Column("targeting_status", String(32), nullable=False),
        Column("evidence_quality", String(20), nullable=False),
        Column("evidence_reference", String(512), nullable=False),
        Column("evidence_sha256", String(64)),
        Column("observed_modalities", String(128), nullable=False),
        Column("rubric_observability", String(24), nullable=False),
        Column("reviewed_by", String(128), nullable=False),
        Column("reviewed_at", String(40), nullable=False),
        ForeignKeyConstraint(["tenant_id","content_id"],
                             ["content_items.tenant_id","content_items.id"]),
    )
    return sources, posts


def upgrade():
    conn = op.get_bind()
    for table in _tables():
        if inspect(conn).has_table(table.name):
            raise RuntimeError("scientific corpus migration already applied outside Alembic")
        conn.execute(CreateTable(table))


def downgrade():
    conn = op.get_bind()
    for table in reversed(_tables()):
        conn.execute(DropTable(table))
