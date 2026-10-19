"""Add idempotency_key to whatsapp_messages

Revision ID: 002_add_message_idempotency_key
Revises: 001_initial_tables
Create Date: 2026-10-18 23:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_add_message_idempotency_key"
down_revision: Union[str, None] = "001_initial_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("whatsapp_messages", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_index("ix_whatsapp_messages_idempotency_key", "whatsapp_messages", ["idempotency_key"])
    op.create_index("ix_whatsapp_messages_clinic_idemp", "whatsapp_messages", ["clinic_id", "idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_messages_clinic_idemp", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_idempotency_key", table_name="whatsapp_messages")
    op.drop_column("whatsapp_messages", "idempotency_key")
