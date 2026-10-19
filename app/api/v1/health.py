from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Verifica a integridade dos serviços internos da API."
)
async def health_check() -> HealthResponse:
    services = {"api": "healthy"}

    # Teste de conexão com o banco de dados
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        services["database"] = "healthy"
    except Exception as exc:
        services["database"] = f"unhealthy: {type(exc).__name__}"

    return HealthResponse(
        status="healthy" if all("healthy" in v for v in services.values()) else "degraded",
        version="0.1.0",
        services=services
    )
