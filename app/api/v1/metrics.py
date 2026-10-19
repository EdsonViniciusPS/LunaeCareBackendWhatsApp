from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from redis import Redis

from app.core.config import settings
from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant_context
from app.models.connection import WhatsAppConnection
from app.models.entities import (
    WhatsAppAutomationRule,
    WhatsAppContact,
    WhatsAppConversation,
    WhatsAppJob,
    WhatsAppMessage,
)

router = APIRouter(prefix="/metrics", tags=["Observabilidade e Métricas"])


@router.get(
    "",
    summary="Métricas operacionais da clínica",
    description="Retorna contadores de conexões, mensagens, entregas, falhas e automações ativas com isolamento multi-tenant."
)
async def get_clinic_metrics(
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    clinic_id = tenant.clinic_id

    # 1. Conexões por status
    conn_query = (
        select(WhatsAppConnection.status, func.count(WhatsAppConnection.id))
        .where(WhatsAppConnection.clinic_id == clinic_id)
        .group_by(WhatsAppConnection.status)
    )
    conn_res = await db.execute(conn_query)
    connections_by_status = dict(conn_res.all())

    # 2. Mensagens por status
    msg_query = (
        select(WhatsAppMessage.status, func.count(WhatsAppMessage.id))
        .where(WhatsAppMessage.clinic_id == clinic_id)
        .group_by(WhatsAppMessage.status)
    )
    msg_res = await db.execute(msg_query)
    messages_by_status = dict(msg_res.all())

    # 3. Mensagens por direção (inbound vs outbound)
    dir_query = (
        select(WhatsAppMessage.direction, func.count(WhatsAppMessage.id))
        .where(WhatsAppMessage.clinic_id == clinic_id)
        .group_by(WhatsAppMessage.direction)
    )
    dir_res = await db.execute(dir_query)
    messages_by_direction = dict(dir_res.all())

    # 4. Total de conversas e contatos
    conv_count_q = select(func.count(WhatsAppConversation.id)).where(WhatsAppConversation.clinic_id == clinic_id)
    contact_count_q = select(func.count(WhatsAppContact.id)).where(WhatsAppContact.clinic_id == clinic_id)
    total_conversations = (await db.execute(conv_count_q)).scalar() or 0
    total_contacts = (await db.execute(contact_count_q)).scalar() or 0

    # 5. Automações ativas vs inativas
    auto_q = (
        select(WhatsAppAutomationRule.enabled, func.count(WhatsAppAutomationRule.id))
        .where(WhatsAppAutomationRule.clinic_id == clinic_id)
        .group_by(WhatsAppAutomationRule.enabled)
    )
    auto_res = await db.execute(auto_q)
    automations_map = dict(auto_res.all())

    # 6. Jobs pendentes / falhos
    jobs_q = (
        select(WhatsAppJob.status, func.count(WhatsAppJob.id))
        .where(WhatsAppJob.clinic_id == clinic_id)
        .group_by(WhatsAppJob.status)
    )
    jobs_res = await db.execute(jobs_q)
    jobs_by_status = dict(jobs_res.all())

    return {
        "clinic_id": clinic_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "connections": {
            "total": sum(connections_by_status.values()),
            "by_status": connections_by_status
        },
        "messages": {
            "total": sum(messages_by_status.values()),
            "by_status": messages_by_status,
            "by_direction": messages_by_direction
        },
        "conversations": total_conversations,
        "contacts": total_contacts,
        "automations": {
            "active": automations_map.get(1, 0),
            "paused": automations_map.get(0, 0)
        },
        "jobs": {
            "total": sum(jobs_by_status.values()),
            "by_status": jobs_by_status
        }
    }


@router.get(
    "/system-health",
    summary="Health check aprofundado dos subsistemas",
    description="Verifica conectividade com PostgreSQL e Redis."
)
async def get_system_health(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    # 1. Testa banco
    db_ok = False
    try:
        await db.execute(select(1))
        db_ok = True
    except Exception:
        pass

    # 2. Testa Redis
    redis_ok = False
    try:
        r = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.1, socket_timeout=0.1)
        r.ping()
        redis_ok = True
    except Exception:
        pass

    overall_status = "healthy" if db_ok else "unhealthy"
    return {
        "status": overall_status,
        "database": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected (offline or fallback mode)",
        "provider": settings.WHATSAPP_PROVIDER,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
