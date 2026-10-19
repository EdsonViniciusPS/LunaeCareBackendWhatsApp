import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import Column, String, DateTime, Text, Enum, Index
from app.core.database import Base


class ConnectionStatus(str, enum.Enum):
    PENDING = "pending"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    DELETING = "deleting"


class WhatsAppConnection(Base):
    __tablename__ = "whatsapp_connections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    clinic_id = Column(String(64), nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="evolution")
    provider_instance_id = Column(String(64), nullable=False, unique=True, index=True)
    phone_number = Column(String(32), nullable=True)
    status = Column(
        String(32),
        nullable=False,
        default=ConnectionStatus.PENDING.value,
        index=True
    )
    # Credencial da instância no provedor, criptografada em repouso (Fernet)
    provider_token_encrypted = Column(Text, nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=True)
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

    __table_args__ = (
        Index("ix_whatsapp_connections_clinic_status", "clinic_id", "status"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "clinic_id": self.clinic_id,
            "provider": self.provider,
            "provider_instance_id": self.provider_instance_id,
            "phone_number": self.phone_number,
            "status": self.status,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
