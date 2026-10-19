import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import WhatsAppWebhookEvent


class WebhookEventRepository:
    """
    Repositório para persistência durável e deduplicação de eventos de webhook.
    Garante idempotência através do event_key único.
    """

    async def get_by_event_key(
        self,
        db: AsyncSession,
        event_key: str
    ) -> Optional[WhatsAppWebhookEvent]:
        query = select(WhatsAppWebhookEvent).where(
            WhatsAppWebhookEvent.event_key == event_key
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def record_event(
        self,
        db: AsyncSession,
        connection_id: Optional[str],
        event_type: str,
        event_key: str,
        payload: Dict[str, Any]
    ) -> Tuple[WhatsAppWebhookEvent, bool]:
        """
        Retorna (event, is_new).
        Se já existir um evento com esse event_key, retorna (event_existente, False).
        """
        existing = await self.get_by_event_key(db, event_key)
        if existing:
            return existing, False

        now = datetime.now(timezone.utc)
        event = WhatsAppWebhookEvent(
            id=str(uuid.uuid4()),
            connection_id=connection_id,
            event_type=event_type,
            event_key=event_key,
            payload=payload,
            received_at=now,
            status="received"
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event, True

    async def mark_processed(
        self,
        db: AsyncSession,
        event_id: str,
        status: str = "processed",
        error_code: Optional[str] = None
    ) -> Optional[WhatsAppWebhookEvent]:
        query = select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.id == event_id)
        result = await db.execute(query)
        event = result.scalar_one_or_none()
        if event:
            event.status = status
            event.error_code = error_code
            event.processed_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(event)
        return event
