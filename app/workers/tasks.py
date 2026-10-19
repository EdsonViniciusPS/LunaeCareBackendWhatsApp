import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.connection import WhatsAppConnection, ConnectionStatus
from app.models.entities import WhatsAppMessage, WhatsAppConversation, WhatsAppContact, WhatsAppJob
from app.providers import get_whatsapp_provider

logger = logging.getLogger(__name__)


async def execute_send_message(message_id: str, clinic_id: str) -> bool:
    """
    Executa o despacho de uma mensagem enfileirada no provedor WhatsApp.
    Atualiza o estado da mensagem e do respectivo job.
    """
    async with AsyncSessionLocal() as db:
        # Busca mensagem
        query = (
            select(WhatsAppMessage)
            .where(
                WhatsAppMessage.id == message_id,
                WhatsAppMessage.clinic_id == clinic_id
            )
        )
        res = await db.execute(query)
        message = res.scalar_one_or_none()
        if not message:
            logger.error("Mensagem %s não encontrada para a clínica %s", message_id, clinic_id)
            return False

        # Busca conversa e contato para obter o número de telefone de destino
        conv_query = (
            select(WhatsAppConversation)
            .options(selectinload(WhatsAppConversation.contact))
            .where(
                WhatsAppConversation.id == message.conversation_id,
                WhatsAppConversation.clinic_id == clinic_id
            )
        )
        conv_res = await db.execute(conv_query)
        conversation = conv_res.scalar_one_or_none()
        if not conversation or not conversation.contact:
            logger.error("Conversa ou contato não encontrado para a mensagem %s", message_id)
            message.status = "failed"
            await db.commit()
            return False

        # Busca conexão
        conn_query = select(WhatsAppConnection).where(
            WhatsAppConnection.id == message.connection_id,
            WhatsAppConnection.clinic_id == clinic_id
        )
        conn_res = await db.execute(conn_query)
        connection = conn_res.scalar_one_or_none()
        if not connection or connection.status != ConnectionStatus.CONNECTED.value:
            logger.warning(
                "Conexão %s não está no estado 'connected'. Cancelando envio da mensagem %s",
                message.connection_id, message_id
            )
            message.status = "failed"
            await db.commit()
            return False

        # Busca job para atualizar tentativas
        job_query = select(WhatsAppJob).where(
            WhatsAppJob.message_id == message_id,
            WhatsAppJob.clinic_id == clinic_id
        )
        job_res = await db.execute(job_query)
        job = job_res.scalar_one_or_none()
        if job:
            job.attempts += 1
            job.started_at = datetime.now(timezone.utc)
            job.status = "running"
            await db.commit()

        provider = get_whatsapp_provider()
        try:
            result = await provider.send_text_message(
                instance_name=connection.provider_instance_id,
                recipient=conversation.contact.phone_number,
                text=message.content or ""
            )

            # Extrai o provider_message_id retornado pela Evolution API
            provider_msg_id = None
            if isinstance(result, dict):
                key = result.get("key")
                if isinstance(key, dict):
                    provider_msg_id = key.get("id")
                elif "id" in result:
                    provider_msg_id = result.get("id")

            now = datetime.now(timezone.utc)
            message.transition_status_to("sent")
            message.sent_at = now
            message.provider_message_id = provider_msg_id
            conversation.last_message_at = now

            if job:
                job.status = "finished"
                job.finished_at = now

            await db.commit()
            logger.info("Mensagem %s despachada com sucesso. Provider ID: %s", message_id, provider_msg_id)
            return True

        except Exception as exc:
            logger.error("Falha ao despachar mensagem %s pelo provedor: %s", message_id, exc)
            now = datetime.now(timezone.utc)
            message.transition_status_to("failed")
            if job:
                job.status = "failed"
                job.finished_at = now
                job.last_error = str(exc)[:500]
            await db.commit()
            return False


def run_send_message_job(message_id: str, clinic_id: str) -> bool:
    """
    Função de entrada síncrona para workers RQ.
    """
    return asyncio.run(execute_send_message(message_id, clinic_id))


async def execute_process_due_jobs(clinic_id: Optional[str] = None) -> int:
    """
    Processa lembretes agendados pendentes (geral ou filtrado por clínica).
    """
    from app.services.scheduling_service import SchedulingService
    from app.repositories.automation_repository import AutomationRepository
    from app.repositories.job_repository import JobRepository
    from app.repositories.contact_repository import ContactRepository
    from app.repositories.connection_repository import ConnectionRepository
    from app.repositories.conversation_repository import ConversationRepository
    from app.repositories.message_repository import MessageRepository
    from app.services.consent_service import ConsentService
    from app.services.messaging_service import MessagingService
    from app.providers import get_whatsapp_provider

    async with AsyncSessionLocal() as db:
        automation_repo = AutomationRepository()
        job_repo = JobRepository()
        contact_repo = ContactRepository()
        consent_service = ConsentService(job_repo=job_repo)
        messaging_service = MessagingService(
            connection_repo=ConnectionRepository(),
            contact_repo=contact_repo,
            conversation_repo=ConversationRepository(),
            message_repo=MessageRepository(),
            provider=get_whatsapp_provider()
        )
        service = SchedulingService(
            automation_repo=automation_repo,
            job_repo=job_repo,
            contact_repo=contact_repo,
            consent_service=consent_service,
            messaging_service=messaging_service
        )
        results = await service.process_due_jobs(db, clinic_id=clinic_id)
        return len(results)


def run_process_due_jobs(clinic_id: Optional[str] = None) -> int:
    return asyncio.run(execute_process_due_jobs(clinic_id=clinic_id))
