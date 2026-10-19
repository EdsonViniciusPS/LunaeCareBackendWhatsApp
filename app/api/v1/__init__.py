from fastapi import APIRouter
from app.api.v1.automations import router as automations_router
from app.api.v1.connections import router as connections_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.health import router as health_router
from app.api.v1.messages import router as messages_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter(prefix="/api/v1")

# O healthcheck fica em /api/v1/health
api_v1_router.include_router(health_router)

# As rotas de WhatsApp ficam prefixadas com /api/v1/whatsapp
whatsapp_router = APIRouter(prefix="/whatsapp")
whatsapp_router.include_router(connections_router)
whatsapp_router.include_router(messages_router)
whatsapp_router.include_router(conversations_router)
whatsapp_router.include_router(automations_router)
whatsapp_router.include_router(metrics_router)
whatsapp_router.include_router(webhooks_router)

api_v1_router.include_router(whatsapp_router)

__all__ = ["api_v1_router"]
