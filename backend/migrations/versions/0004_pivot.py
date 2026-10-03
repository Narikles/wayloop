"""nouvel angle : candidatures centralisées, pipeline, notes, automatisations, assistant

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03 12:26:43
"""
from alembic import op
import sqlalchemy as sa
import app.db


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('inbound_emails',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('message_hash', sa.String(length=64), nullable=False),
    sa.Column('recruitment_id', sa.String(length=36), nullable=True),
    sa.Column('application_id', sa.String(length=36), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('detail', sa.String(length=255), nullable=True),
    sa.Column('received_at', app.db.UTCDateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inbound_emails_message_hash'), 'inbound_emails', ['message_hash'], unique=True)
    op.create_table('candidate_notes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('application_id', sa.String(length=36), nullable=False),
    sa.Column('author_id', sa.String(length=36), nullable=True),
    sa.Column('text', app.db.EncryptedText(), nullable=False),
    sa.Column('created_at', app.db.UTCDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_candidate_notes_application_id'), 'candidate_notes', ['application_id'], unique=False)
    op.add_column('applications', sa.Column('added_by', sa.String(length=36), nullable=True))
    op.add_column('applications', sa.Column('seen_at', app.db.UTCDateTime(timezone=True), nullable=True))
    op.add_column('applications', sa.Column('relance_sent_at', app.db.UTCDateTime(timezone=True), nullable=True))
    op.add_column('applications', sa.Column('rejection_due_at', app.db.UTCDateTime(timezone=True), nullable=True))
    op.add_column('applications', sa.Column('rejection_sent_at', app.db.UTCDateTime(timezone=True), nullable=True))
    op.add_column('applications', sa.Column('status_before_rejection', sa.String(length=30), nullable=True))
    op.add_column('companies', sa.Column('automations', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column('companies', sa.Column('last_recap_at', app.db.UTCDateTime(timezone=True), nullable=True))
    op.add_column('usage_records', sa.Column('company_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_usage_records_company_id'), 'usage_records', ['company_id'], unique=False)
    # Candidatures déjà traitées : elles ne reviennent pas dans la colonne « Reçu » du pipeline.
    op.execute("UPDATE applications SET seen_at = created_at WHERE status <> 'received'")


def downgrade() -> None:
    with op.batch_alter_table('usage_records') as batch:
        batch.drop_index('ix_usage_records_company_id')
        batch.drop_column('company_id')
    with op.batch_alter_table('companies') as batch:
        batch.drop_column('last_recap_at')
        batch.drop_column('automations')
    with op.batch_alter_table('applications') as batch:
        batch.drop_column('status_before_rejection')
        batch.drop_column('rejection_sent_at')
        batch.drop_column('rejection_due_at')
        batch.drop_column('relance_sent_at')
        batch.drop_column('seen_at')
        batch.drop_column('added_by')
    op.drop_index(op.f('ix_candidate_notes_application_id'), table_name='candidate_notes')
    op.drop_table('candidate_notes')
    op.drop_index(op.f('ix_inbound_emails_message_hash'), table_name='inbound_emails')
    op.drop_table('inbound_emails')
