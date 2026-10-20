"""Add concurrency and unique constraints for messages and conversations

Revision ID: 004_add_concurrency_and_unique_constraints
Revises: 003_add_job_appointment_and_payload
Create Date: 2026-10-19 11:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004_add_concurrency_constraints"
down_revision: Union[str, None] = "003_add_job_appointment_payload"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Torna único o índice de idempotência de mensagens por clínica
    op.drop_index("ix_whatsapp_messages_clinic_idemp", table_name="whatsapp_messages")
    op.create_index(
        "ix_whatsapp_messages_clinic_idemp",
        "whatsapp_messages",
        ["clinic_id", "idempotency_key"],
        unique=True
    )

    # 2. Garante unicidade de conversa por (clínica, conexão, contato)
    op.create_index(
        "uq_whatsapp_conversations_clinic_conn_contact",
        "whatsapp_conversations",
        ["clinic_id", "connection_id", "contact_id"],
        unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_whatsapp_conversations_clinic_conn_contact", table_name="whatsapp_conversations")
    op.drop_index("ix_whatsapp_messages_clinic_idemp", table_name="whatsapp_messages")
    op.create_index(
        "ix_whatsapp_messages_clinic_idemp",
        "whatsapp_messages",
        ["clinic_id", "idempotency_key"]
    )
