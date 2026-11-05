"""CAP-023 E8 — explicit embedded source-audio rights and quality profiles.

Revision ID: 0011_studio_source_audio_hq_e8
Revises: 0010_studio_multitrack_e7
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_studio_source_audio_hq_e8"
down_revision = "0010_studio_multitrack_e7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("studio_e7_video_sources") as batch:
        batch.add_column(sa.Column("has_embedded_audio", sa.Integer(), nullable=False,
                                   server_default="0"))
        batch.add_column(sa.Column("embedded_audio_rights_status", sa.String(16),
                                   nullable=False, server_default="not_attested"))
        batch.add_column(sa.Column("embedded_audio_evidence_reference", sa.String(512),
                                   nullable=True))


def downgrade():
    with op.batch_alter_table("studio_e7_video_sources") as batch:
        batch.drop_column("embedded_audio_evidence_reference")
        batch.drop_column("embedded_audio_rights_status")
        batch.drop_column("has_embedded_audio")
