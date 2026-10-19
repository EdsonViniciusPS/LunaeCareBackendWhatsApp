import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import WhatsAppContactPreference


class ConsentRepository:
    """
    Repositório de gestão de preferências e consentimento (LGPD) com isolamento multi-tenant.
    """

    async def get_preference(
        self,
        db: AsyncSession,
        clinic_id: str,
        contact_id: str,
        purpose: str = "appointment_reminders"
    ) -> Optional[WhatsAppContactPreference]:
        query = select(WhatsAppContactPreference).where(
            WhatsAppContactPreference.clinic_id == clinic_id,
            WhatsAppContactPreference.contact_id == contact_id,
            WhatsAppContactPreference.purpose == purpose
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def set_preference(
        self,
        db: AsyncSession,
        clinic_id: str,
        contact_id: str,
        consent_status: str,
        source: Optional[str] = None,
        purpose: str = "appointment_reminders"
    ) -> WhatsAppContactPreference:
        now = datetime.now(timezone.utc)
        pref = await self.get_preference(db, clinic_id, contact_id, purpose=purpose)
        if pref:
            pref.consent_status = consent_status
            pref.consent_source = source or pref.consent_source
            if consent_status == "opted_out":
                pref.opted_out_at = now
            elif consent_status == "opted_in":
                pref.consented_at = now
            pref.updated_at = now
            await db.commit()
            await db.refresh(pref)
            return pref

        new_pref = WhatsAppContactPreference(
            id=str(uuid.uuid4()),
            clinic_id=clinic_id,
            contact_id=contact_id,
            purpose=purpose,
            consent_status=consent_status,
            consent_source=source,
            consented_at=now if consent_status == "opted_in" else None,
            opted_out_at=now if consent_status == "opted_out" else None,
            updated_at=now
        )
        db.add(new_pref)
        await db.commit()
        await db.refresh(new_pref)
        return new_pref

    async def is_opted_out(
        self,
        db: AsyncSession,
        clinic_id: str,
        contact_id: str,
        purpose: str = "appointment_reminders"
    ) -> bool:
        pref = await self.get_preference(db, clinic_id, contact_id, purpose=purpose)
        return pref is not None and pref.consent_status == "opted_out"
