"""Add appointment_id and payload to whatsapp_jobs

Revision ID: 003_add_job_appointment_and_payload
Revises: 002_add_message_idempotency_key
Create Date: 2026-10-18 23:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_add_job_appointment_and_payload"
down_revision: Union[str, None] = "002_add_message_idempotency_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("whatsapp_jobs", sa.Column("appointment_id", sa.String(length=64), nullable=True))
    op.add_column("whatsapp_jobs", sa.Column("payload", sa.JSON(), nullable=True))
    op.create_index("ix_whatsapp_jobs_appointment_id", "whatsapp_jobs", ["appointment_id"])
    op.create_index("ix_whatsapp_jobs_clinic_status", "whatsapp_jobs", ["clinic_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_whatsapp_jobs_clinic_status", table_name="whatsapp_jobs")
    op.drop_index("ix_whatsapp_jobs_appointment_id", table_name="whatsapp_jobs")
    op.drop_column("whatsapp_jobs", "payload")
    op.drop_column("whatsapp_jobs", "appointment_id")
