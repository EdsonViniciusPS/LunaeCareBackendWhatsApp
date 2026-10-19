from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.tenancy import TenantContext, get_tenant_context
from app.providers import get_whatsapp_provider
from app.providers.base import WhatsAppProvider
from app.repositories.connection_repository import ConnectionRepository
from app.services.connection_service import ConnectionService
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionResponse,
    ConnectionConnectResponse,
    ConnectionDisconnectResponse,
    ConnectionDeleteResponse
)

router = APIRouter(prefix="/connections", tags=["Conexões WhatsApp"])


def get_connection_service(
    provider: WhatsAppProvider = Depends(get_whatsapp_provider)
) -> ConnectionService:
    repository = ConnectionRepository()
    return ConnectionService(repository=repository, provider=provider)


@router.post(
    "",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar conexão WhatsApp",
    description="Provisiona uma nova conexão de WhatsApp isolada para a clínica autenticada."
)
async def create_connection(
    data: Optional[ConnectionCreate] = None,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: ConnectionService = Depends(get_connection_service),
) -> ConnectionResponse:
    connection = await service.create_connection(db, clinic_id=tenant.clinic_id, data=data)
    return ConnectionResponse.model_validate(connection)


@router.get(
    "",
    response_model=List[ConnectionResponse],
    summary="Listar conexões da clínica",
    description="Retorna todas as conexões cadastradas para a clínica autenticada."
)
async def list_connections(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: ConnectionService = Depends(get_connection_service),
) -> List[ConnectionResponse]:
    connections = await service.list_connections(
        db, clinic_id=tenant.clinic_id, skip=skip, limit=limit
    )
    return [ConnectionResponse.model_validate(conn) for conn in connections]


@router.get(
    "/{connection_id}",
    response_model=ConnectionResponse,
    summary="Consultar estado da conexão",
    description="Obtém os detalhes e estado atualizado da conexão informada."
)
async def get_connection(
    connection_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: ConnectionService = Depends(get_connection_service),
) -> ConnectionResponse:
    connection = await service.get_connection(
        db, connection_id=connection_id, clinic_id=tenant.clinic_id
    )
    return ConnectionResponse.model_validate(connection)


@router.post(
    "/{connection_id}/connect",
    response_model=ConnectionConnectResponse,
    summary="Iniciar conexão e gerar QR Code",
    description="Inicia o pareamento no WhatsApp e retorna o QR Code em base64 e código de pareamento."
)
async def connect(
    connection_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: ConnectionService = Depends(get_connection_service),
) -> ConnectionConnectResponse:
    return await service.connect(
        db, connection_id=connection_id, clinic_id=tenant.clinic_id
    )


@router.post(
    "/{connection_id}/disconnect",
    response_model=ConnectionDisconnectResponse,
    summary="Desconectar conexão",
    description="Desconecta a sessão ativa do WhatsApp para a conexão especificada."
)
async def disconnect(
    connection_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: ConnectionService = Depends(get_connection_service),
) -> ConnectionDisconnectResponse:
    return await service.disconnect(
        db, connection_id=connection_id, clinic_id=tenant.clinic_id
    )


@router.delete(
    "/{connection_id}",
    response_model=ConnectionDeleteResponse,
    summary="Remover conexão",
    description="Exclui a conexão no banco de dados e limpa a respectiva instância no provedor."
)
async def delete_connection(
    connection_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: AsyncSession = Depends(get_db),
    service: ConnectionService = Depends(get_connection_service),
) -> ConnectionDeleteResponse:
    return await service.delete(
        db, connection_id=connection_id, clinic_id=tenant.clinic_id
    )
