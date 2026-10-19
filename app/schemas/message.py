from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class MessageSendRequest(BaseModel):
    connection_id: str = Field(..., description="ID da conexão ativa do WhatsApp")
    recipient: str = Field(..., min_length=8, max_length=32, description="Número de telefone do destinatário com DDI e DDD (ex: 5511999998888)")
    content: str = Field(..., min_length=1, max_length=4096, description="Conteúdo da mensagem em texto simples")
    type: str = Field(default="text", description="Tipo da mensagem (ex: text)")
    idempotency_key: Optional[str] = Field(default=None, max_length=128, description="Chave de idempotência para evitar envios duplicados")


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    clinic_id: str
    connection_id: str
    conversation_id: str
    provider_message_id: Optional[str] = None
    direction: str
    type: str
    content: Optional[str] = None
    status: str
    idempotency_key: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
