"""Initial tables for Lunae Care WhatsApp Backend

Revision ID: 001_initial_tables
Revises: 
Create Date: 2026-10-18 22:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. whatsapp_connections
    op.create_table(
        "whatsapp_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("clinic_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="evolution"),
        sa.Column("provider_instance_id", sa.String(length=64), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("provider_token_encrypted", sa.Text(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_instance_id")
    )
    op.create_index("ix_whatsapp_connections_clinic_id", "whatsapp_connections", ["clinic_id"])
    op.create_index("ix_whatsapp_connections_provider_instance_id", "whatsapp_connections", ["provider_instance_id"])
    op.create_index("ix_whatsapp_connections_clinic_status", "whatsapp_connections", ["clinic_id", "status"])

    # 2. whatsapp_contacts
    op.create_table(
        "whatsapp_contacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("clinic_id", sa.String(length=64), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("patient_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index("ix_whatsapp_contacts_clinic_id", "whatsapp_contacts", ["clinic_id"])
    op.create_index("ix_whatsapp_contacts_clinic_phone", "whatsapp_contacts", ["clinic_id", "phone_number"], unique=True)

    # 3. whatsapp_conversations
    op.create_table(
        "whatsapp_conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("clinic_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("whatsapp_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", sa.String(length=36), sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("assigned_user_id", sa.String(length=64), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index("ix_whatsapp_conversations_clinic_contact", "whatsapp_conversations", ["clinic_id", "contact_id"])

    # 4. whatsapp_messages
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("clinic_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("whatsapp_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("whatsapp_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_message_id", sa.String(length=128), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index("ix_whatsapp_messages_clinic_conv", "whatsapp_messages", ["clinic_id", "conversation_id"])

    # 5. whatsapp_webhook_events
    op.create_table(
        "whatsapp_webhook_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key")
    )

    # 6. whatsapp_jobs
    op.create_table(
        "whatsapp_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("clinic_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id")
    )

    # 7. whatsapp_contact_preferences
    op.create_table(
        "whatsapp_contact_preferences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("clinic_id", sa.String(length=64), nullable=False),
        sa.Column("contact_id", sa.String(length=36), sa.ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("consent_status", sa.String(length=32), nullable=False, server_default="opted_in"),
        sa.Column("consent_source", sa.String(length=64), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id")
    )

    # 8. whatsapp_automation_rules
    op.create_table(
        "whatsapp_automation_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("clinic_id", sa.String(length=64), nullable=False),
        sa.Column("connection_id", sa.String(length=36), sa.ForeignKey("whatsapp_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_trigger", sa.String(length=64), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id")
    )


def downgrade() -> None:
    op.drop_table("whatsapp_automation_rules")
    op.drop_table("whatsapp_contact_preferences")
    op.drop_table("whatsapp_jobs")
    op.drop_table("whatsapp_webhook_events")
    op.drop_table("whatsapp_messages")
    op.drop_table("whatsapp_conversations")
    op.drop_table("whatsapp_contacts")
    op.drop_table("whatsapp_connections")
