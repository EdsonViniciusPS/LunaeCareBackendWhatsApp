from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import WhatsAppMessage


class MessageRepository:
    """
    Repositório de persistência de mensagens WhatsApp com isolamento multi-tenant estrito por clínica.
    """

    async def get_by_id(
        self,
        db: AsyncSession,
        message_id: str,
        clinic_id: str
    ) -> Optional[WhatsAppMessage]:
        query = select(WhatsAppMessage).where(
            WhatsAppMessage.id == message_id,
            WhatsAppMessage.clinic_id == clinic_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self,
        db: AsyncSession,
        clinic_id: str,
        idempotency_key: str
    ) -> Optional[WhatsAppMessage]:
        query = select(WhatsAppMessage).where(
            WhatsAppMessage.clinic_id == clinic_id,
            WhatsAppMessage.idempotency_key == idempotency_key
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_provider_message_id(
        self,
        db: AsyncSession,
        provider_message_id: str
    ) -> Optional[WhatsAppMessage]:
        query = select(WhatsAppMessage).where(
            WhatsAppMessage.provider_message_id == provider_message_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_by_conversation(
        self,
        db: AsyncSession,
        clinic_id: str,
        conversation_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[WhatsAppMessage]:
        query = (
            select(WhatsAppMessage)
            .where(
                WhatsAppMessage.clinic_id == clinic_id,
                WhatsAppMessage.conversation_id == conversation_id
            )
            .order_by(WhatsAppMessage.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        message: WhatsAppMessage
    ) -> WhatsAppMessage:
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message

    async def update(
        self,
        db: AsyncSession,
        message: WhatsAppMessage
    ) -> WhatsAppMessage:
        await db.commit()
        await db.refresh(message)
        return message
