import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import normalize_phone
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
        clinic_id: Optional[str] = None,
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
        )
        if clinic_id:
            query = query.where(WhatsAppJob.clinic_id == clinic_id)

        query = query.order_by(WhatsAppJob.scheduled_at.asc()).limit(limit)

        # Em PostgreSQL, aplica trava de linha SKIP LOCKED para impedir disputa de concorrência entre múltiplos workers
        try:
            bind = db.sync_session.bind
            if bind and bind.dialect.name == "postgresql":
                query = query.with_for_update(skip_locked=True)
        except Exception:
            pass

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
        Compara o telefone normalizado com 'recipient' e 'phone_number' no payload.
        """
        now = datetime.now(timezone.utc)
        target_phone = normalize_phone(phone_number)
        if not target_phone:
            return 0

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
            job_phone = payload.get("recipient") or payload.get("phone_number")
            if job_phone and normalize_phone(job_phone) == target_phone:
                job.status = "cancelled"
                job.finished_at = now
                job.last_error = "Paciente solicitou opt-out"
                count += 1
        if count > 0:
            await db.commit()
        return count
