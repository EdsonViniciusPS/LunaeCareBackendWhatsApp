import hmac
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant_context
from app.providers import get_whatsapp_provider
from app.providers.base import WhatsAppProvider
from app.repositories.automation_repository import AutomationRepository
from app.repositories.connection_repository import ConnectionRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.job_repository import JobRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.automation import (
    AgendaEventPayload,
    AutomationRuleCreate,
    AutomationRuleResponse,
    AutomationRuleToggleAllRequest,
    AutomationRuleUpdate,
)
from app.services.consent_service import ConsentService
from app.services.messaging_service import MessagingService
from app.services.scheduling_service import SchedulingService

router = APIRouter(prefix="/automations", tags=["Automações e Agenda Inteligente"])


def get_scheduling_service(
    provider: WhatsAppProvider = Depends(get_whatsapp_provider),
) -> SchedulingService:
    connection_repo = ConnectionRepository()
    contact_repo = ContactRepository()
    conv_repo = ConversationRepository()
    msg_repo = MessageRepository()
    automation_repo = AutomationRepository()
    job_repo = JobRepository()

    consent_service = ConsentService(job_repo=job_repo)
    messaging_service = MessagingService(
        connection_repo=connection_repo,
        contact_repo=contact_repo,
        conversation_repo=conv_repo,
        message_repo=msg_repo,
        provider=provider
    )

    return SchedulingService(
        automation_repo=automation_repo,
        job_repo=job_repo,
        contact_repo=contact_repo,
        consent_service=consent_service,
        messaging_service=messaging_service
    )


@router.get(
    "",
    response_model=List[AutomationRuleResponse],
    summary="Listar regras de automação",
    description="Retorna todas as regras de automação da clínica autenticada."
)
async def list_rules(
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(get_scheduling_service),
) -> List[AutomationRuleResponse]:
    rules = await service.list_rules(db, clinic_id=tenant.clinic_id)
    return [AutomationRuleResponse.model_validate(r) for r in rules]


@router.post(
    "",
    response_model=AutomationRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar regra de automação",
    description="Cadastra uma nova regra automática (ex: confirmação imediata, lembrete 24h antes, cancelamento)."
)
async def create_rule(
    body: AutomationRuleCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(get_scheduling_service),
) -> AutomationRuleResponse:
    rule = await service.create_rule(db, clinic_id=tenant.clinic_id, data=body)
    return AutomationRuleResponse.model_validate(rule)


@router.get(
    "/{rule_id}",
    response_model=AutomationRuleResponse,
    summary="Consultar regra de automação",
    description="Obtém detalhes de uma regra específica da clínica."
)
async def get_rule(
    rule_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(get_scheduling_service),
) -> AutomationRuleResponse:
    rule = await service.get_rule(db, clinic_id=tenant.clinic_id, rule_id=rule_id)
    return AutomationRuleResponse.model_validate(rule)


@router.put(
    "/{rule_id}",
    response_model=AutomationRuleResponse,
    summary="Atualizar regra de automação",
    description="Modifica o template, gatilho ou estado de ativação de uma regra existente."
)
async def update_rule(
    rule_id: str,
    body: AutomationRuleUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(get_scheduling_service),
) -> AutomationRuleResponse:
    rule = await service.update_rule(db, clinic_id=tenant.clinic_id, rule_id=rule_id, data=body)
    return AutomationRuleResponse.model_validate(rule)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Excluir regra de automação"
)
async def delete_rule(
    rule_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(get_scheduling_service),
) -> None:
    await service.delete_rule(db, clinic_id=tenant.clinic_id, rule_id=rule_id)


@router.post(
    "/pause",
    summary="Pausar ou reativar todas as automações da clínica",
    description="Permite interromper imediatamente todos os envios automáticos da clínica de forma centralizada."
)
async def toggle_all_automations(
    body: AutomationRuleToggleAllRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(get_scheduling_service),
) -> Dict[str, Any]:
    count = await service.toggle_all_rules(db, clinic_id=tenant.clinic_id, enabled=body.enabled)
    action = "reativadas" if body.enabled else "pausadas"
    return {
        "status": "success",
        "action": action,
        "affected_rules": count,
        "clinic_id": tenant.clinic_id
    }


@router.post(
    "/agenda-events",
    summary="Receber eventos da agenda do Lunae Care",
    description="Endpoint chamado quando consultas são criadas, reagendadas ou canceladas para acionar lembretes e automações."
)
async def receive_agenda_event(
    event: AgendaEventPayload,
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(get_scheduling_service),
) -> Dict[str, Any]:
    # Suporta autenticação tanto via token interno de microsserviço quanto via JWT Bearer
    clinic_id: Optional[str] = None
    if x_internal_token and hmac.compare_digest(x_internal_token, settings.INTERNAL_API_KEY):
        clinic_id = event.clinic_id
        if not clinic_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="clinic_id é obrigatório ao usar autenticação interna de microsserviço."
            )
    elif authorization and authorization.startswith("Bearer "):
        from app.core.security import decode_access_token
        try:
            token = authorization.split(" ", 1)[1]
            claims = decode_access_token(token)
            clinic_id = claims.get(settings.JWT_CLINIC_CLAIM)
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação necessária.")

    if not clinic_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Clínica não identificada.")

    return await service.handle_agenda_event(db, clinic_id=clinic_id, event=event)


@router.post(
    "/process-due-jobs",
    summary="Processar lembretes agendados pendentes",
    description="Dispara o envio de lembretes cujo horário agendado chegou (scheduled_at <= now), validando opt-out. Restrito a chamadas internas ou com escopo estrito à clínica autenticada."
)
async def process_due_jobs_endpoint(
    clinic_id: Optional[str] = Query(default=None, description="Filtrar por clínica específica (permitido apenas para token interno)"),
    x_internal_token: Optional[str] = Header(default=None, alias="X-Internal-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(get_scheduling_service),
) -> Dict[str, Any]:
    target_clinic_id: Optional[str] = None

    # 1. Autenticação interna de sistema (ex: cron ou worker periódico)
    if x_internal_token and hmac.compare_digest(x_internal_token, settings.INTERNAL_API_KEY):
        target_clinic_id = clinic_id
    # 2. Autenticação via JWT Bearer (escopo estritamente restrito à clínica do token)
    elif authorization and authorization.startswith("Bearer "):
        from app.core.security import decode_access_token
        try:
            claims = decode_access_token(authorization.split(" ", 1)[1])
            target_clinic_id = claims.get(settings.JWT_CLINIC_CLAIM)
            if not target_clinic_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token sem clínica autorizada.")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autorizado. Forneça o header X-Internal-Token ou token de autorização Bearer."
        )

    processed = await service.process_due_jobs(db, clinic_id=target_clinic_id)
    return {
        "processed_count": len(processed),
        "clinic_id": target_clinic_id,
        "results": processed
    }
