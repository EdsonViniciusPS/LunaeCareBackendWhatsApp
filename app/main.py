from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.logging_filter import SensitiveDataSanitizerFilter

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
# Aplica sanitizador de segredos a todos os handlers de log
for handler in logging.root.handlers:
    handler.addFilter(SensitiveDataSanitizerFilter())

logger = logging.getLogger("lunaecare-whatsapp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando Lunae Care WhatsApp Backend (%s)...", settings.ENVIRONMENT)

    # Cria tabelas caso esteja rodando com SQLite em desenvolvimento ou testes locais
    if settings.DATABASE_URL.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Tabelas SQLite sincronizadas.")

    yield

    logger.info("Encerrando serviços e conexões...")
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    description="Backend para integração WhatsApp multiempresa das clínicas do Lunae Care.",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# Headers de segurança HTTP e proteção contra clickjacking/sniffing
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Configuração de CORS restrita
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://app.lunaecare.com.br"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Inclusão dos roteadores da API v1
app.include_router(api_v1_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Erro não tratado na requisição %s: %s", request.url.path, exc, exc_info=settings.DEBUG)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Ocorreu um erro interno no servidor. Nenhuma informação confidencial foi exposta."}
    )


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/docs" if settings.DEBUG else None
    }
