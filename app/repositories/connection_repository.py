from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import WhatsAppConnection


class ConnectionRepository:
    """
    Repositório de persistência para conexões WhatsApp com isolamento multi-tenant estrito.
    """

    async def get_by_id(
        self,
        db: AsyncSession,
        connection_id: str,
        clinic_id: str
    ) -> Optional[WhatsAppConnection]:
        query = select(WhatsAppConnection).where(
            WhatsAppConnection.id == connection_id,
            WhatsAppConnection.clinic_id == clinic_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_instance_id(
        self,
        db: AsyncSession,
        instance_id: str
    ) -> Optional[WhatsAppConnection]:
        query = select(WhatsAppConnection).where(
            WhatsAppConnection.provider_instance_id == instance_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_by_clinic(
        self,
        db: AsyncSession,
        clinic_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[WhatsAppConnection]:
        query = (
            select(WhatsAppConnection)
            .where(WhatsAppConnection.clinic_id == clinic_id)
            .order_by(WhatsAppConnection.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        connection: WhatsAppConnection
    ) -> WhatsAppConnection:
        db.add(connection)
        await db.commit()
        await db.refresh(connection)
        return connection

    async def update(
        self,
        db: AsyncSession,
        connection: WhatsAppConnection
    ) -> WhatsAppConnection:
        await db.commit()
        await db.refresh(connection)
        return connection

    async def delete(
        self,
        db: AsyncSession,
        connection: WhatsAppConnection
    ) -> None:
        await db.delete(connection)
        await db.commit()
