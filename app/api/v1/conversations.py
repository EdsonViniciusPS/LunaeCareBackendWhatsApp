from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant_context
from app.providers import get_whatsapp_provider
from app.providers.base import WhatsAppProvider
from app.repositories.connection_repository import ConnectionRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.conversation import ConversationResponse
from app.schemas.message import MessageResponse
from app.services.messaging_service import MessagingService

router = APIRouter(prefix="/conversations", tags=["Conversas WhatsApp"])


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


@router.get(
    "",
    response_model=List[ConversationResponse],
    summary="Listar conversas da clínica",
    description="Retorna a lista paginada de conversas pertencentes exclusivamente à clínica autenticada."
)
async def list_conversations(
    connection_id: Optional[str] = Query(None, description="Filtrar por conexão específica"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: MessagingService = Depends(get_messaging_service),
) -> List[ConversationResponse]:
    conversations = await service.list_conversations(
        db, clinic_id=tenant.clinic_id, connection_id=connection_id, skip=skip, limit=limit
    )
    return [ConversationResponse.model_validate(conv) for conv in conversations]


@router.get(
    "/{conversation_id}/messages",
    response_model=List[MessageResponse],
    summary="Consultar mensagens de uma conversa",
    description="Retorna o histórico de mensagens de uma conversa autorizada para a clínica autenticada."
)
async def list_messages(
    conversation_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: MessagingService = Depends(get_messaging_service),
) -> List[MessageResponse]:
    messages = await service.list_conversation_messages(
        db, clinic_id=tenant.clinic_id, conversation_id=conversation_id, skip=skip, limit=limit
    )
    return [MessageResponse.model_validate(msg) for msg in messages]
