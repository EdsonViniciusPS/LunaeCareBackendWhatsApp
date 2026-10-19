from typing import Optional
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import rate_limit_messages
from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant_context
from app.providers import get_whatsapp_provider
from app.providers.base import WhatsAppProvider
from app.repositories.connection_repository import ConnectionRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.message import MessageSendRequest, MessageResponse
from app.services.messaging_service import MessagingService

router = APIRouter(prefix="/messages", tags=["Mensagens WhatsApp"])


def get_messaging_service(
    provider: WhatsAppProvider = Depends(get_whatsapp_provider),
) -> MessagingService:
    return MessagingService(
        connection_repo=ConnectionRepository(),
        contact_repo=ContactRepository(),
        conversation_repo=ConversationRepository(),
        message_repo=MessageRepository(),
        provider=provider
    )


@router.post(
    "",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_messages)],
    summary="Enfileirar envio de mensagem",
    description="Registra a mensagem com estado 'queued', valida permissões da clínica e despacha de forma assíncrona com idempotência e rate limiting."
)
async def send_message(
    body: MessageSendRequest,
    x_idempotency_key: Optional[str] = Header(default=None, alias="X-Idempotency-Key"),
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: MessagingService = Depends(get_messaging_service),
) -> MessageResponse:
    effective_idempotency = x_idempotency_key or body.idempotency_key
    message = await service.send_message(
        db,
        clinic_id=tenant.clinic_id,
        request=body,
        idempotency_key=effective_idempotency
    )
    return MessageResponse.model_validate(message)
