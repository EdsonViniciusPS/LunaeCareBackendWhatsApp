import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import WhatsAppContact


class ContactRepository:
    """
    Repositório para contatos WhatsApp com isolamento multi-tenant estrito por clínica.
    """

    async def get_by_id(
        self,
        db: AsyncSession,
        contact_id: str,
        clinic_id: str
    ) -> Optional[WhatsAppContact]:
        query = select(WhatsAppContact).where(
            WhatsAppContact.id == contact_id,
            WhatsAppContact.clinic_id == clinic_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_phone(
        self,
        db: AsyncSession,
        clinic_id: str,
        phone_number: str
    ) -> Optional[WhatsAppContact]:
        query = select(WhatsAppContact).where(
            WhatsAppContact.clinic_id == clinic_id,
            WhatsAppContact.phone_number == phone_number
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        db: AsyncSession,
        clinic_id: str,
        phone_number: str,
        display_name: Optional[str] = None,
        patient_id: Optional[str] = None
    ) -> WhatsAppContact:
        contact = await self.get_by_phone(db, clinic_id, phone_number)
        if contact:
            if display_name and contact.display_name != display_name:
                contact.display_name = display_name
                await db.commit()
                await db.refresh(contact)
            return contact

        new_contact = WhatsAppContact(
            id=str(uuid.uuid4()),
            clinic_id=clinic_id,
            phone_number=phone_number,
            display_name=display_name,
            patient_id=patient_id
        )
        db.add(new_contact)
        await db.commit()
        await db.refresh(new_contact)
        return new_contact
