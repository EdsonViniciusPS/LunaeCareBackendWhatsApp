import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import WhatsAppJob


class JobRepository:
    """
    Repositório de persistência de jobs assíncronos e agendados com isolamento multi-tenant.
    """

    async def get_by_id(
        self,
        db: AsyncSession,
        job_id: str,
        clinic_id: str
    ) -> Optional[WhatsAppJob]:
        query = select(WhatsAppJob).where(
            WhatsAppJob.id == job_id,
            WhatsAppJob.clinic_id == clinic_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        job: WhatsAppJob
    ) -> WhatsAppJob:
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    async def update(
        self,
        db: AsyncSession,
        job: WhatsAppJob
    ) -> WhatsAppJob:
        await db.commit()
        await db.refresh(job)
        return job

    async def get_due_jobs(
        self,
        db: AsyncSession,
        reference_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[WhatsAppJob]:
        now = reference_time or datetime.now(timezone.utc)
        query = (
            select(WhatsAppJob)
            .where(
                WhatsAppJob.status == "pending",
                WhatsAppJob.scheduled_at <= now
            )
            .order_by(WhatsAppJob.scheduled_at.asc())
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    async def cancel_jobs_for_appointment(
        self,
        db: AsyncSession,
        clinic_id: str,
        appointment_id: str
    ) -> int:
        now = datetime.now(timezone.utc)
        stmt = (
            update(WhatsAppJob)
            .where(
                WhatsAppJob.clinic_id == clinic_id,
                WhatsAppJob.appointment_id == appointment_id,
                WhatsAppJob.status == "pending"
            )
            .values(
                status="cancelled",
                finished_at=now,
                last_error="Consulta alterada ou cancelada na agenda"
            )
        )
        res = await db.execute(stmt)
        await db.commit()
        return res.rowcount

    async def cancel_jobs_for_phone(
        self,
        db: AsyncSession,
        clinic_id: str,
        phone_number: str
    ) -> int:
        """
        Cancela jobs pendentes quando um paciente solicita opt-out.
        """
        now = datetime.now(timezone.utc)
        query = (
            select(WhatsAppJob)
            .where(
                WhatsAppJob.clinic_id == clinic_id,
                WhatsAppJob.status == "pending"
            )
        )
        result = await db.execute(query)
        jobs = result.scalars().all()
        count = 0
        for job in jobs:
            payload = job.payload or {}
            if payload.get("phone_number") == phone_number:
                job.status = "cancelled"
                job.finished_at = now
                job.last_error = "Paciente solicitou opt-out"
                count += 1
        if count > 0:
            await db.commit()
        return count
