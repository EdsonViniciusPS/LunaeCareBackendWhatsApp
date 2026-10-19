import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import WhatsAppAutomationRule


class AutomationRepository:
    """
    Repositório para regras de automação com isolamento estrito por clínica.
    """

    async def get_by_id(
        self,
        db: AsyncSession,
        rule_id: str,
        clinic_id: str
    ) -> Optional[WhatsAppAutomationRule]:
        query = select(WhatsAppAutomationRule).where(
            WhatsAppAutomationRule.id == rule_id,
            WhatsAppAutomationRule.clinic_id == clinic_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def list_by_clinic(
        self,
        db: AsyncSession,
        clinic_id: str
    ) -> List[WhatsAppAutomationRule]:
        query = (
            select(WhatsAppAutomationRule)
            .where(WhatsAppAutomationRule.clinic_id == clinic_id)
            .order_by(WhatsAppAutomationRule.created_at.desc())
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_active_rule_by_trigger(
        self,
        db: AsyncSession,
        clinic_id: str,
        event_trigger: str
    ) -> Optional[WhatsAppAutomationRule]:
        query = (
            select(WhatsAppAutomationRule)
            .where(
                WhatsAppAutomationRule.clinic_id == clinic_id,
                WhatsAppAutomationRule.event_trigger == event_trigger,
                WhatsAppAutomationRule.enabled == 1
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        rule: WhatsAppAutomationRule
    ) -> WhatsAppAutomationRule:
        db.add(rule)
        await db.commit()
        await db.refresh(rule)
        return rule

    async def update(
        self,
        db: AsyncSession,
        rule: WhatsAppAutomationRule
    ) -> WhatsAppAutomationRule:
        rule.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(rule)
        return rule

    async def delete(
        self,
        db: AsyncSession,
        rule: WhatsAppAutomationRule
    ) -> None:
        await db.delete(rule)
        await db.commit()

    async def toggle_all_for_clinic(
        self,
        db: AsyncSession,
        clinic_id: str,
        enabled: bool
    ) -> int:
        val = 1 if enabled else 0
        stmt = (
            update(WhatsAppAutomationRule)
            .where(WhatsAppAutomationRule.clinic_id == clinic_id)
            .values(enabled=val, updated_at=datetime.now(timezone.utc))
        )
        res = await db.execute(stmt)
        await db.commit()
        return res.rowcount
