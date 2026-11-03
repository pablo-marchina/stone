"""Manual corpus sampling registry; grants and metadata remain separate.

Revision ID: 0004_corpus_profiles
Revises: 0003_ingestion_page_checkpoints
"""
from alembic import op
from sqlalchemy import (MetaData,Table,Column,String,ForeignKeyConstraint,inspect)
from sqlalchemy.schema import CreateTable,DropTable

revision='0004_corpus_profiles'
down_revision='0003_ingestion_page_checkpoints'
branch_labels=None
depends_on=None


def _table():
    md=MetaData()
    Table('ingestion_source_grants',md,
          Column('tenant_id',String(128),primary_key=True),
          Column('platform',String(32),primary_key=True),
          Column('source_account_id',String(128),primary_key=True))
    return Table('corpus_profiles',md,
        Column('tenant_id',String(128),primary_key=True),
        Column('platform',String(32),primary_key=True),
        Column('source_account_id',String(128),primary_key=True),
        Column('sector',String(24),nullable=False),
        Column('sampling_stratum',String(80),nullable=False),
        Column('evidence_reference',String(512),nullable=False),
        Column('registered_at',String(40),nullable=False),
        ForeignKeyConstraint(['tenant_id','platform','source_account_id'],[
            'ingestion_source_grants.tenant_id',
            'ingestion_source_grants.platform',
            'ingestion_source_grants.source_account_id']))


def upgrade():
    conn=op.get_bind()
    table=_table()
    if inspect(conn).has_table(table.name):
        raise RuntimeError('corpus registry table already exists outside Alembic')
    conn.execute(CreateTable(table))


def downgrade():
    op.get_bind().execute(DropTable(_table()))
