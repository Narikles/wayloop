"""sans IA ni WhatsApp, thème de l'interface

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # États retirés (description libre, choix des canaux) : ramenés au brouillon d'offre.
    op.execute("UPDATE recruitments SET state = 'offer_review' "
               "WHERE state IN ('brief', 'profile_review', 'ready_to_publish')")
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('theme', sa.String(length=10), nullable=False, server_default='light'))
        batch.drop_index('ix_users_phone')
        batch.drop_column('preferred_channel')
        batch.drop_column('whatsapp_last_inbound_at')
    with op.batch_alter_table('recruitments') as batch:
        batch.drop_column('brief_text')
        batch.drop_column('open_questions')


def downgrade() -> None:
    with op.batch_alter_table('recruitments') as batch:
        batch.add_column(sa.Column('open_questions', sa.JSON(), nullable=False, server_default='[]'))
        batch.add_column(sa.Column('brief_text', sa.Text(), nullable=True))
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('whatsapp_last_inbound_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('preferred_channel', sa.String(length=20), nullable=False, server_default='email'))
        batch.create_index('ix_users_phone', ['phone'], unique=False)
        batch.drop_column('theme')
