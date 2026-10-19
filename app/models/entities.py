import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, JSON, Integer, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base


class WhatsAppContact(Base):
    __tablename__ = "whatsapp_contacts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clinic_id = Column(String(64), nullable=False, index=True)
    phone_number = Column(String(32), nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    patient_id = Column(String(64), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_whatsapp_contacts_clinic_phone", "clinic_id", "phone_number", unique=True),
    )


class WhatsAppConversation(Base):
    __tablename__ = "whatsapp_conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clinic_id = Column(String(64), nullable=False, index=True)
    connection_id = Column(String(36), ForeignKey("whatsapp_connections.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(String(36), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(32), nullable=False, default="open")
    assigned_user_id = Column(String(64), nullable=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    contact = relationship("WhatsAppContact", lazy="joined")

    __table_args__ = (
        Index("ix_whatsapp_conversations_clinic_contact", "clinic_id", "contact_id"),
        Index("uq_whatsapp_conversations_clinic_conn_contact", "clinic_id", "connection_id", "contact_id", unique=True),
    )


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clinic_id = Column(String(64), nullable=False, index=True)
    connection_id = Column(String(36), ForeignKey("whatsapp_connections.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(String(36), ForeignKey("whatsapp_conversations.id", ondelete="CASCADE"), nullable=False)
    provider_message_id = Column(String(128), nullable=True, index=True)
    direction = Column(String(16), nullable=False)  # inbound | outbound
    type = Column(String(32), nullable=False, default="text")
    content = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="queued")
    idempotency_key = Column(String(128), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_whatsapp_messages_clinic_conv", "clinic_id", "conversation_id"),
        Index("ix_whatsapp_messages_clinic_idemp", "clinic_id", "idempotency_key", unique=True),
    )

    def transition_status_to(self, new_status: str) -> bool:
        """
        Avança o status da mensagem de forma estritamente monotônica.
        Retorna True se o status foi alterado, ou False se a transição foi ignorada.
        """
        from app.core.status import should_transition_message_status
        if should_transition_message_status(self.status, new_status):
            self.status = new_status
            return True
        return False


class WhatsAppWebhookEvent(Base):
    __tablename__ = "whatsapp_webhook_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    connection_id = Column(String(36), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    event_key = Column(String(128), nullable=False, unique=True, index=True)
    payload = Column(JSON, nullable=True)
    received_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    processed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, default="received")
    error_code = Column(String(64), nullable=True)


class WhatsAppJob(Base):
    __tablename__ = "whatsapp_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clinic_id = Column(String(64), nullable=False, index=True)
    connection_id = Column(String(36), nullable=False)
    message_id = Column(String(36), nullable=True)
    appointment_id = Column(String(64), nullable=True, index=True)
    job_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)


class WhatsAppContactPreference(Base):
    __tablename__ = "whatsapp_contact_preferences"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clinic_id = Column(String(64), nullable=False, index=True)
    contact_id = Column(String(36), ForeignKey("whatsapp_contacts.id", ondelete="CASCADE"), nullable=False)
    purpose = Column(String(64), nullable=False)
    consent_status = Column(String(32), nullable=False, default="opted_in")
    consent_source = Column(String(64), nullable=True)
    consented_at = Column(DateTime(timezone=True), nullable=True)
    opted_out_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )


class WhatsAppAutomationRule(Base):
    __tablename__ = "whatsapp_automation_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clinic_id = Column(String(64), nullable=False, index=True)
    connection_id = Column(String(36), ForeignKey("whatsapp_connections.id", ondelete="CASCADE"), nullable=False)
    event_trigger = Column(String(64), nullable=False)
    template = Column(Text, nullable=False)
    enabled = Column(Integer, nullable=False, default=1)
    settings = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
