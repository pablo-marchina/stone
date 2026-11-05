"""IMP-187/188: tenant-scoped storyboard and versioned timeline contracts.

Revision ID: 0008_studio_storyboards
Revises: 0007_studio_e1
"""
from alembic import op
from sqlalchemy import (MetaData, Table, Column, String, Integer, Text,
                        ForeignKeyConstraint, inspect)
from sqlalchemy.schema import CreateTable, DropTable

revision="0008_studio_storyboards"
down_revision="0007_studio_e1"
branch_labels=None
depends_on=None


def _tables():
    meta=MetaData()
    Table('studio_documents',meta,Column('tenant_id',String(128),primary_key=True),
          Column('document_id',String(128),primary_key=True))
    story=Table('studio_storyboards',meta,
        Column('tenant_id',String(128),primary_key=True),
        Column('storyboard_id',String(128),primary_key=True),
        Column('source_document_id',String(128),nullable=False),
        Column('current_version',Integer,nullable=False),
        ForeignKeyConstraint(['tenant_id','source_document_id'],
            ['studio_documents.tenant_id','studio_documents.document_id']))
    versions=Table('studio_storyboard_versions',meta,
        Column('tenant_id',String(128),primary_key=True),
        Column('storyboard_id',String(128),primary_key=True),
        Column('version',Integer,primary_key=True),
        Column('payload',Text,nullable=False),
        Column('edited_by',String(128),nullable=False),
        Column('created_at',String(48),nullable=False),
        ForeignKeyConstraint(['tenant_id','storyboard_id'],
            ['studio_storyboards.tenant_id','studio_storyboards.storyboard_id']))
    return story,versions


def upgrade():
    connection=op.get_bind()
    for table in _tables():
        if inspect(connection).has_table(table.name):
            raise RuntimeError('STORYBOARD_TABLE_ALREADY_EXISTS_OUTSIDE_ALEMBIC')
        connection.execute(CreateTable(table))


def downgrade():
    connection=op.get_bind()
    for table in reversed(_tables()):
        connection.execute(DropTable(table))
