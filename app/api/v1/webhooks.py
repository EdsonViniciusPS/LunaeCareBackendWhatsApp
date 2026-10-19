from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.providers import get_whatsapp_provider
from app.providers.base import WhatsAppProvider
from app.repositories.connection_repository import ConnectionRepository
from app.services.webhook_service import WebhookService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

MAX_WEBHOOK_BYTES = 1_000_000


@router.post(
    "/evolution/{provider_key}",
    summary="Receber eventos da Evolution API",
    description="Autenticado pela chave HMAC exclusiva da instância presente na URL."
)
async def evolution_webhook(
    provider_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_whatsapp_provider),
):
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload muito grande.")

    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido.")

    service = WebhookService(ConnectionRepository(), provider=provider)
    ok = await service.handle_evolution_event(db, provider_key, payload)
    if not ok:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook não autorizado.")
    return {"received": True}
