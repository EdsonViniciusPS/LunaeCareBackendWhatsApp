import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import WhatsAppConnection, ConnectionStatus
from app.models.entities import WhatsAppMessage, WhatsAppConversation, WhatsAppContact, WhatsAppJob
from app.providers.base import WhatsAppProvider
from app.repositories.connection_repository import ConnectionRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.message import MessageSendRequest
from app.core.phone import normalize_phone
from app.workers.queue import enqueue_message_send

logger = logging.getLogger(__name__)


def clean_phone_number(raw_phone: str) -> str:
    """Normaliza o telefone para apenas dígitos e valida o tamanho."""
    cleaned = normalize_phone(raw_phone)
    if len(cleaned) < 10 or len(cleaned) > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT if hasattr(status, "HTTP_422_UNPROCESSABLE_CONTENT") else 422,
            detail="Número de telefone inválido. Informe o número com código do país e DDD (ex: 5511999998888)."
        )
    return cleaned


class MessagingService:
    """
    Serviço responsável por regras de envio, listagem de conversas e mensagens com isolamento multi-tenant.
    """

    def __init__(
        self,
        connection_repo: ConnectionRepository,
        contact_repo: ContactRepository,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        provider: WhatsAppProvider
    ):
        self.connection_repo = connection_repo
        self.contact_repo = contact_repo
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self.provider = provider

    async def send_message(
        self,
        db: AsyncSession,
        clinic_id: str,
        request: MessageSendRequest,
        idempotency_key: Optional[str] = None
    ) -> WhatsAppMessage:
        effective_idempotency_key = idempotency_key or request.idempotency_key

        # 1. Verificação de idempotência
        if effective_idempotency_key:
            existing = await self.message_repo.get_by_idempotency_key(
                db, clinic_id, effective_idempotency_key
            )
            if existing:
                logger.info("Retornando mensagem já existente para chave de idempotência %s", effective_idempotency_key)
                return existing

        # 2. Valida conexão da clínica
        connection = await self.connection_repo.get_by_id(db, request.connection_id, clinic_id)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conexão não encontrada para esta clínica."
            )

        if connection.status != ConnectionStatus.CONNECTED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"A conexão não está ativa (estado atual: {connection.status}). Não é possível enviar mensagens."
            )

        # 3. Sanitiza destinatário
        clean_recipient = clean_phone_number(request.recipient)

        # 4. Obtém ou cria contato
        contact = await self.contact_repo.get_or_create(
            db, clinic_id=clinic_id, phone_number=clean_recipient
        )

        # 5. Obtém ou cria conversa
        conversation = await self.conversation_repo.get_or_create(
            db, clinic_id=clinic_id, connection_id=connection.id, contact_id=contact.id
        )

        # 6. Registra a mensagem como 'queued'
        now = datetime.now(timezone.utc)
        message = WhatsAppMessage(
            id=str(uuid.uuid4()),
            clinic_id=clinic_id,
            connection_id=connection.id,
            conversation_id=conversation.id,
            direction="outbound",
            type=request.type,
            content=request.content,
            status="queued",
            idempotency_key=effective_idempotency_key,
            created_at=now
        )
        try:
            saved_message = await self.message_repo.create(db, message)
        except IntegrityError:
            await db.rollback()
            if effective_idempotency_key:
                existing = await self.message_repo.get_by_idempotency_key(
                    db, clinic_id, effective_idempotency_key
                )
                if existing:
                    logger.info("Retornando mensagem existente após colisão de concorrência na chave %s", effective_idempotency_key)
                    return existing
            raise

        # 7. Registra job de processamento
        job = WhatsAppJob(
            id=str(uuid.uuid4()),
            clinic_id=clinic_id,
            connection_id=connection.id,
            message_id=saved_message.id,
            job_type="send_message",
            status="pending",
            attempts=0,
            scheduled_at=now
        )
        db.add(job)
        await db.commit()

        # 8. Despacho assíncrono via Redis RQ ou fallback direto (ex: testes/modo mock)
        enqueued = enqueue_message_send(saved_message.id, clinic_id)
        if not enqueued:
            # Fallback direto via provedor para execução síncrona / testes
            try:
                result = await self.provider.send_text_message(
                    instance_name=connection.provider_instance_id,
                    recipient=clean_recipient,
                    text=request.content
                )
                provider_msg_id = None
                if isinstance(result, dict):
                    key = result.get("key")
                    if isinstance(key, dict):
                        provider_msg_id = key.get("id")
                    elif "id" in result:
                        provider_msg_id = result.get("id")

                saved_message.transition_status_to("sent")
                saved_message.sent_at = datetime.now(timezone.utc)
                saved_message.provider_message_id = provider_msg_id
                job.status = "finished"
                job.finished_at = saved_message.sent_at
                await self.message_repo.update(db, saved_message)
                await db.commit()
            except Exception as exc:
                logger.error("Falha ao despachar mensagem pelo provedor: %s", exc)
                saved_message.transition_status_to("failed")
                job.status = "failed"
                job.last_error = str(exc)[:500]
                await self.message_repo.update(db, saved_message)
                await db.commit()

        await self.conversation_repo.update_last_message(db, conversation, now)
        return saved_message

    async def list_conversations(
        self,
        db: AsyncSession,
        clinic_id: str,
        connection_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[WhatsAppConversation]:
        return await self.conversation_repo.list_by_clinic(
            db, clinic_id=clinic_id, connection_id=connection_id, skip=skip, limit=limit
        )

    async def get_conversation(
        self,
        db: AsyncSession,
        clinic_id: str,
        conversation_id: str
    ) -> WhatsAppConversation:
        conversation = await self.conversation_repo.get_by_id(db, conversation_id, clinic_id)
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversa não encontrada para esta clínica."
            )
        return conversation

    async def list_conversation_messages(
        self,
        db: AsyncSession,
        clinic_id: str,
        conversation_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[WhatsAppMessage]:
        # Valida propriedade da conversa
        await self.get_conversation(db, clinic_id, conversation_id)
        return await self.message_repo.list_by_conversation(
            db, clinic_id=clinic_id, conversation_id=conversation_id, skip=skip, limit=limit
        )
