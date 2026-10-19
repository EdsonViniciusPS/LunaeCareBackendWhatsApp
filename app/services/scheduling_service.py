import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import normalize_phone
from app.models.entities import WhatsAppAutomationRule, WhatsAppJob
from app.repositories.automation_repository import AutomationRepository
from app.repositories.connection_repository import ConnectionRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.job_repository import JobRepository
from app.schemas.automation import (
    AgendaEventPayload,
    AutomationRuleCreate,
    AutomationRuleUpdate,
)
from app.schemas.message import MessageSendRequest
from app.services.consent_service import ConsentService
from app.services.messaging_service import MessagingService

logger = logging.getLogger(__name__)


def render_template(template: str, context: Dict[str, Any]) -> str:
    """
    Substitui placeholders seguros como {{patient_name}}, {{professional_name}},
    {{appointment_date}}, {{appointment_time}} sem dados clínicos sensíveis.
    """
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered


class SchedulingService:
    """
    Serviço que orquestra a automação da agenda inteligente: confirmações, lembretes,
    cancelamentos e execução agendada respeitando opt-out.
    """

    def __init__(
        self,
        automation_repo: AutomationRepository,
        job_repo: JobRepository,
        contact_repo: ContactRepository,
        consent_service: ConsentService,
        messaging_service: MessagingService,
        connection_repo: Optional[ConnectionRepository] = None,
    ):
        self.automation_repo = automation_repo
        self.job_repo = job_repo
        self.contact_repo = contact_repo
        self.consent_service = consent_service
        self.messaging_service = messaging_service
        self.connection_repo = connection_repo or (
            getattr(messaging_service, "connection_repo", None) or ConnectionRepository()
        )

    async def create_rule(
        self,
        db: AsyncSession,
        clinic_id: str,
        data: AutomationRuleCreate
    ) -> WhatsAppAutomationRule:
        connection = await self.connection_repo.get_by_id(db, data.connection_id, clinic_id)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conexão não encontrada para esta clínica."
            )

        rule = WhatsAppAutomationRule(
            id=str(uuid.uuid4()),
            clinic_id=clinic_id,
            connection_id=data.connection_id,
            event_trigger=data.event_trigger,
            template=data.template,
            enabled=data.enabled,
            settings=data.settings,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        return await self.automation_repo.create(db, rule)

    async def list_rules(
        self,
        db: AsyncSession,
        clinic_id: str
    ) -> List[WhatsAppAutomationRule]:
        return await self.automation_repo.list_by_clinic(db, clinic_id)

    async def get_rule(
        self,
        db: AsyncSession,
        clinic_id: str,
        rule_id: str
    ) -> WhatsAppAutomationRule:
        rule = await self.automation_repo.get_by_id(db, rule_id, clinic_id)
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Regra de automação não encontrada para esta clínica."
            )
        return rule

    async def update_rule(
        self,
        db: AsyncSession,
        clinic_id: str,
        rule_id: str,
        data: AutomationRuleUpdate
    ) -> WhatsAppAutomationRule:
        rule = await self.get_rule(db, clinic_id, rule_id)
        if data.connection_id is not None:
            connection = await self.connection_repo.get_by_id(db, data.connection_id, clinic_id)
            if not connection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conexão não encontrada para esta clínica."
                )
            rule.connection_id = data.connection_id
        if data.event_trigger is not None:
            rule.event_trigger = data.event_trigger
        if data.template is not None:
            rule.template = data.template
        if data.enabled is not None:
            rule.enabled = data.enabled
        if data.settings is not None:
            rule.settings = data.settings
        return await self.automation_repo.update(db, rule)

    async def delete_rule(
        self,
        db: AsyncSession,
        clinic_id: str,
        rule_id: str
    ) -> None:
        rule = await self.get_rule(db, clinic_id, rule_id)
        await self.automation_repo.delete(db, rule)

    async def toggle_all_rules(
        self,
        db: AsyncSession,
        clinic_id: str,
        enabled: bool
    ) -> int:
        return await self.automation_repo.toggle_all_for_clinic(db, clinic_id, enabled)

    async def handle_agenda_event(
        self,
        db: AsyncSession,
        clinic_id: str,
        event: AgendaEventPayload
    ) -> Dict[str, Any]:
        """
        Recebe e processa eventos da agenda Lunae Care (created, rescheduled, cancelled).
        """
        clean_phone = normalize_phone(event.phone_number)
        apt_dt = event.appointment_datetime
        context = {
            "patient_name": event.patient_name,
            "professional_name": event.professional_name,
            "appointment_date": apt_dt.strftime("%d/%m/%Y"),
            "appointment_time": apt_dt.strftime("%H:%M"),
            "appointment_id": event.appointment_id
        }

        # 1. Tratamento de cancelamento de consulta
        if event.event == "appointment.cancelled":
            cancelled_count = await self.job_repo.cancel_jobs_for_appointment(
                db, clinic_id, event.appointment_id
            )
            logger.info("Consulta %s cancelada. %d jobs pendentes cancelados.", event.appointment_id, cancelled_count)

            # Verifica se há regra para envio de aviso de cancelamento
            cancel_rule = await self.automation_repo.get_active_rule_by_trigger(
                db, clinic_id, "appointment_cancelled"
            )
            if cancel_rule:
                content = render_template(cancel_rule.template, context)
                await self.messaging_service.send_message(
                    db,
                    clinic_id=clinic_id,
                    request=MessageSendRequest(
                        connection_id=cancel_rule.connection_id,
                        recipient=clean_phone,
                        content=content,
                        idempotency_key=f"cancel_{event.appointment_id}"
                    )
                )
            return {
                "status": "cancelled",
                "jobs_cancelled": cancelled_count,
                "appointment_id": event.appointment_id
            }

        # 2. Tratamento de reagendamento de consulta
        if event.event == "appointment.rescheduled":
            cancelled_count = await self.job_repo.cancel_jobs_for_appointment(
                db, clinic_id, event.appointment_id
            )
            logger.info("Consulta %s reagendada. Lembretes antigos cancelados: %d", event.appointment_id, cancelled_count)

        # 3. Confirmação imediata para appointment.created
        created_rule = await self.automation_repo.get_active_rule_by_trigger(
            db, clinic_id, "appointment_created"
        )
        if created_rule and event.event == "appointment.created":
            content = render_template(created_rule.template, context)
            await self.messaging_service.send_message(
                db,
                clinic_id=clinic_id,
                request=MessageSendRequest(
                    connection_id=created_rule.connection_id,
                    recipient=clean_phone,
                    content=content,
                    idempotency_key=f"created_{event.appointment_id}"
                )
            )

        # 4. Agendamento do lembrete (ex: 24 horas antes)
        reminder_rule = await self.automation_repo.get_active_rule_by_trigger(
            db, clinic_id, "appointment_reminder_24h"
        )
        scheduled_job_id = None
        if reminder_rule:
            hours_before = 24
            if reminder_rule.settings and "hours_before" in reminder_rule.settings:
                hours_before = int(reminder_rule.settings["hours_before"])

            reminder_time = apt_dt - timedelta(hours=hours_before)
            now = datetime.now(timezone.utc)

            # Se a consulta estiver no futuro, agenda o job (se o tempo de antecedência já passou, agenda para envio imediato)
            if apt_dt > now:
                scheduled_time = max(reminder_time, now)
                job = WhatsAppJob(
                    id=str(uuid.uuid4()),
                    clinic_id=clinic_id,
                    connection_id=reminder_rule.connection_id,
                    appointment_id=event.appointment_id,
                    job_type="appointment_reminder_24h",
                    status="pending",
                    scheduled_at=scheduled_time,
                    payload={
                        "rule_id": reminder_rule.id,
                        "recipient": clean_phone,
                        "phone_number": clean_phone,
                        "patient_name": event.patient_name,
                        "professional_name": event.professional_name,
                        "appointment_date": apt_dt.strftime("%d/%m/%Y"),
                        "appointment_time": apt_dt.strftime("%H:%M"),
                        "appointment_id": event.appointment_id
                    }
                )
                saved_job = await self.job_repo.create(db, job)
                scheduled_job_id = saved_job.id
                logger.info(
                    "Lembrete agendado para consulta %s em %s (Job %s)",
                    event.appointment_id, reminder_time.isoformat(), scheduled_job_id
                )

        return {
            "status": "processed",
            "event": event.event,
            "appointment_id": event.appointment_id,
            "scheduled_reminder_job_id": scheduled_job_id
        }

    async def process_due_jobs(
        self,
        db: AsyncSession,
        clinic_id: Optional[str] = None,
        reference_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Executa os lembretes pendentes cujo horário agendado chegou (scheduled_at <= now).
        Se clinic_id for informado, filtra exclusivamente os jobs daquela clínica.
        Verifica consentimento e opt-out antes de enviar cada mensagem.
        """
        due_jobs = await self.job_repo.get_due_jobs(db, clinic_id=clinic_id, reference_time=reference_time)
        results = []

        for job in due_jobs:
            payload = job.payload or {}
            raw_recipient = payload.get("recipient") or payload.get("phone_number")
            clinic_id = job.clinic_id

            if not raw_recipient:
                job.status = "failed"
                job.last_error = "Payload sem recipient"
                await self.job_repo.update(db, job)
                continue

            recipient = normalize_phone(raw_recipient)

            # Verifica se o paciente solicitou opt-out
            contact = await self.contact_repo.get_by_phone(db, clinic_id, recipient)
            if contact:
                is_opted_out = await self.consent_service.is_opted_out(db, clinic_id, contact.id)
                if is_opted_out:
                    job.status = "cancelled"
                    job.last_error = "Cancelado por opt-out do paciente"
                    job.finished_at = datetime.now(timezone.utc)
                    await self.job_repo.update(db, job)
                    results.append({"job_id": job.id, "status": "cancelled", "reason": "opt_out"})
                    logger.info("Job %s cancelado: paciente optou por não receber mensagens.", job.id)
                    continue

            # Obtém regra de automação
            rule_id = payload.get("rule_id")
            rule = None
            if rule_id:
                rule = await self.automation_repo.get_by_id(db, rule_id, clinic_id)

            template = rule.template if rule else "Lembrete: sua consulta com {{professional_name}} está agendada para {{appointment_date}} às {{appointment_time}}."
            content = render_template(template, payload)

            try:
                msg = await self.messaging_service.send_message(
                    db,
                    clinic_id=clinic_id,
                    request=MessageSendRequest(
                        connection_id=job.connection_id,
                        recipient=recipient,
                        content=content,
                        idempotency_key=f"job_reminder_{job.id}"
                    )
                )
                job.status = "finished"
                job.message_id = msg.id
                job.finished_at = datetime.now(timezone.utc)
                await self.job_repo.update(db, job)
                results.append({"job_id": job.id, "status": "sent", "message_id": msg.id})
                logger.info("Lembrete agendado %s enviado com sucesso.", job.id)
            except Exception as exc:
                job.status = "failed"
                job.last_error = str(exc)[:500]
                job.finished_at = datetime.now(timezone.utc)
                await self.job_repo.update(db, job)
                results.append({"job_id": job.id, "status": "failed", "error": str(exc)})
                logger.error("Erro ao enviar lembrete agendado %s: %s", job.id, exc)

        return results
