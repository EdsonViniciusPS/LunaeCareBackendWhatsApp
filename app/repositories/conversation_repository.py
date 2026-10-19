import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import WhatsAppConversation


from sqlalchemy.exc import IntegrityError


class ConversationRepository:
    """
    Repositório para conversas WhatsApp com isolamento multi-tenant estrito por clínica.
    """

    async def get_by_id(
        self,
        db: AsyncSession,
        conversation_id: str,
        clinic_id: str
    ) -> Optional[WhatsAppConversation]:
        query = (
            select(WhatsAppConversation)
            .options(selectinload(WhatsAppConversation.contact))
            .where(
                WhatsAppConversation.id == conversation_id,
                WhatsAppConversation.clinic_id == clinic_id
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_contact_and_connection(
        self,
        db: AsyncSession,
        clinic_id: str,
        connection_id: str,
        contact_id: str
    ) -> Optional[WhatsAppConversation]:
        query = (
            select(WhatsAppConversation)
            .options(selectinload(WhatsAppConversation.contact))
            .where(
                WhatsAppConversation.clinic_id == clinic_id,
                WhatsAppConversation.connection_id == connection_id,
                WhatsAppConversation.contact_id == contact_id
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        db: AsyncSession,
        clinic_id: str,
        connection_id: str,
        contact_id: str
    ) -> WhatsAppConversation:
        conversation = await self.get_by_contact_and_connection(
            db, clinic_id, connection_id, contact_id
        )
        if conversation:
            return conversation

        now = datetime.now(timezone.utc)
        new_conv = WhatsAppConversation(
            id=str(uuid.uuid4()),
            clinic_id=clinic_id,
            connection_id=connection_id,
            contact_id=contact_id,
            status="open",
            last_message_at=now,
            created_at=now,
            updated_at=now
        )
        db.add(new_conv)
        try:
            await db.commit()
            await db.refresh(new_conv)
            # Recarrega com relationship
            return await self.get_by_id(db, new_conv.id, clinic_id) or new_conv
        except IntegrityError:
            await db.rollback()
            existing = await self.get_by_contact_and_connection(
                db, clinic_id, connection_id, contact_id
            )
            if existing:
                return existing
            raise

    async def list_by_clinic(
        self,
        db: AsyncSession,
        clinic_id: str,
        connection_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[WhatsAppConversation]:
        query = (
            select(WhatsAppConversation)
            .options(selectinload(WhatsAppConversation.contact))
            .where(WhatsAppConversation.clinic_id == clinic_id)
        )
        if connection_id:
            query = query.where(WhatsAppConversation.connection_id == connection_id)

        query = (
            query.order_by(WhatsAppConversation.last_message_at.desc().nullslast())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def update_last_message(
        self,
        db: AsyncSession,
        conversation: WhatsAppConversation,
        timestamp: datetime
    ) -> WhatsAppConversation:
        conversation.last_message_at = timestamp
        conversation.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(conversation)
        return conversation
