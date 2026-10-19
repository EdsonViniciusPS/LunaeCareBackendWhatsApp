import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import encrypt_secret
from app.core.security import derive_webhook_key
from app.models.connection import WhatsAppConnection, ConnectionStatus
from app.providers.base import WhatsAppProvider
from app.repositories.connection_repository import ConnectionRepository
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionConnectResponse,
    ConnectionDisconnectResponse,
    ConnectionDeleteResponse
)

logger = logging.getLogger(__name__)


def _extract_instance_token(create_result: dict) -> Optional[str]:
    """Evolution v1 retorna hash={apikey}, v2 retorna hash='<token>'."""
    h = create_result.get("hash")
    if isinstance(h, dict):
        return h.get("apikey")
    if isinstance(h, str):
        return h
    return None


class ConnectionService:
    """
    Serviço de gerenciamento do ciclo de vida das conexões WhatsApp por clínica.
    """

    def __init__(
        self,
        repository: ConnectionRepository,
        provider: WhatsAppProvider
    ):
        self.repository = repository
        self.provider = provider

    def _generate_instance_id(self) -> str:
        """Gera um ID interno imutável e aleatório, nunca expondo nome da clínica."""
        return f"lunae_{uuid.uuid4().hex[:16]}"

    async def _get_owned(
        self, db: AsyncSession, connection_id: str, clinic_id: str
    ) -> WhatsAppConnection:
        connection = await self.repository.get_by_id(db, connection_id, clinic_id)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conexão não encontrada para esta clínica."
            )
        return connection

    async def create_connection(
        self,
        db: AsyncSession,
        clinic_id: str,
        data: Optional[ConnectionCreate] = None
    ) -> WhatsAppConnection:
        instance_id = self._generate_instance_id()
        # Chave de webhook própria da instância (não o segredo global)
        webhook_url = f"{settings.EVOLUTION_WEBHOOK_URL}/{derive_webhook_key(instance_id)}"

        create_result = await self.provider.create_instance(
            instance_name=instance_id,
            webhook_url=webhook_url
        )

        connection = WhatsAppConnection(
            id=str(uuid.uuid4()),
            clinic_id=clinic_id,
            provider=settings.WHATSAPP_PROVIDER,
            provider_instance_id=instance_id,
            provider_token_encrypted=encrypt_secret(_extract_instance_token(create_result)),
            phone_number=data.phone_number if data else None,
            status=ConnectionStatus.PENDING.value
        )
        return await self.repository.create(db, connection)

    async def get_connection(
        self,
        db: AsyncSession,
        connection_id: str,
        clinic_id: str
    ) -> WhatsAppConnection:
        connection = await self._get_owned(db, connection_id, clinic_id)

        # Sincronização sob demanda com o provedor
        try:
            state_data = await self.provider.get_connection_state(connection.provider_instance_id)
            state = state_data.get("instance", {}).get("state", "").lower()
            if state == "open" and connection.status != ConnectionStatus.CONNECTED.value:
                connection.status = ConnectionStatus.CONNECTED.value
                connection.connected_at = datetime.now(timezone.utc)
                await self.repository.update(db, connection)
            elif state in ("close", "refused") and connection.status == ConnectionStatus.CONNECTED.value:
                connection.status = ConnectionStatus.DISCONNECTED.value
                await self.repository.update(db, connection)
        except Exception as exc:
            logger.warning("Falha ao consultar estado em tempo real no provedor: %s", type(exc).__name__)

        return connection

    async def list_connections(
        self,
        db: AsyncSession,
        clinic_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[WhatsAppConnection]:
        return await self.repository.list_by_clinic(db, clinic_id, skip=skip, limit=limit)

    async def connect(
        self,
        db: AsyncSession,
        connection_id: str,
        clinic_id: str
    ) -> ConnectionConnectResponse:
        connection = await self._get_owned(db, connection_id, clinic_id)

        connect_data = await self.provider.connect(connection.provider_instance_id)

        # QR Code é temporário: repassado ao cliente, nunca persistido nem logado
        qr_code = connect_data.get("base64") or connect_data.get("code")
        pairing_code = connect_data.get("pairingCode")

        connection.status = ConnectionStatus.CONNECTING.value
        await self.repository.update(db, connection)

        return ConnectionConnectResponse(
            connection_id=connection.id,
            status=connection.status,
            qrcode=qr_code,
            pairing_code=pairing_code,
            message="QR Code gerado com sucesso. Escaneie pelo WhatsApp da clínica."
        )

    async def disconnect(
        self,
        db: AsyncSession,
        connection_id: str,
        clinic_id: str
    ) -> ConnectionDisconnectResponse:
        connection = await self._get_owned(db, connection_id, clinic_id)

        await self.provider.disconnect(connection.provider_instance_id)

        connection.status = ConnectionStatus.DISCONNECTED.value
        await self.repository.update(db, connection)

        return ConnectionDisconnectResponse(
            connection_id=connection.id,
            status=connection.status,
            message="WhatsApp desconectado com sucesso."
        )

    async def delete(
        self,
        db: AsyncSession,
        connection_id: str,
        clinic_id: str
    ) -> ConnectionDeleteResponse:
        connection = await self._get_owned(db, connection_id, clinic_id)

        connection.status = ConnectionStatus.DELETING.value
        await self.repository.update(db, connection)

        try:
            await self.provider.delete_instance(connection.provider_instance_id)
        except Exception as exc:
            logger.error("Aviso ao remover instância no provedor: %s", type(exc).__name__)

        await self.repository.delete(db, connection)

        return ConnectionDeleteResponse(
            connection_id=connection_id,
            status="deleted",
            message="Conexão excluída e instância removida do provedor."
        )
