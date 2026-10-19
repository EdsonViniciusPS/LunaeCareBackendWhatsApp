import logging
from typing import Any, Dict, Optional
import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.providers.base import WhatsAppProvider

logger = logging.getLogger(__name__)


class EvolutionProvider(WhatsAppProvider):
    """
    Adaptador para a Evolution API (v2 / v1.8+).
    Encapsula chamadas HTTP e normaliza as respostas para o backend do Lunae Care.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        mock_mode: Optional[bool] = None
    ):
        self.base_url = (base_url or settings.EVOLUTION_API_URL).rstrip("/")
        self.api_key = api_key or settings.EVOLUTION_API_KEY
        self.mock_mode = settings.EVOLUTION_MOCK_MODE if mock_mode is None else mock_mode
        self._mock_instances: Dict[str, Dict[str, Any]] = {}

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.api_key,
            "Content-Type": "application/json"
        }

    async def create_instance(
        self,
        instance_name: str,
        webhook_url: Optional[str] = None
    ) -> Dict[str, Any]:
        if self.mock_mode:
            self._mock_instances[instance_name] = {
                "instanceName": instance_name,
                "state": "close",
                "webhook_url": webhook_url
            }
            return {
                "instance": {"instanceName": instance_name, "status": "created"},
                "hash": {"apikey": f"mock_key_{instance_name}"}
            }

        payload: Dict[str, Any] = {
            "instanceName": instance_name,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
        }
        if webhook_url:
            payload["webhook"] = webhook_url
            payload["webhook_by_events"] = False
            payload["events"] = [
                "CONNECTION_UPDATE",
                "MESSAGES_UPSERT",
                "MESSAGES_UPDATE",
                "QRCODE_UPDATED"
            ]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.base_url}/instance/create",
                    json=payload,
                    headers=self._headers()
                )
                if res.status_code in (200, 201):
                    return res.json()
                elif res.status_code == 403 or "already in use" in res.text:
                    logger.warning("Instância %s já existe na Evolution API.", instance_name)
                    return {"instance": {"instanceName": instance_name, "status": "existing"}}
                else:
                    logger.error("Erro ao criar instância na Evolution API: %s %s", res.status_code, res.text)
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Falha ao provisionar conexão no provedor: {res.text}"
                    )
        except httpx.RequestError as exc:
            logger.error("Falha de conexão com a Evolution API: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Provedor WhatsApp temporariamente inacessível."
            )

    async def connect(
        self,
        instance_name: str
    ) -> Dict[str, Any]:
        if self.mock_mode:
            mock_qr = (
                "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            )
            if instance_name in self._mock_instances:
                self._mock_instances[instance_name]["state"] = "connecting"
            return {
                "base64": mock_qr,
                "code": "2@mocked_evolution_pairing_code",
                "pairingCode": "12345678"
            }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(
                    f"{self.base_url}/instance/connect/{instance_name}",
                    headers=self._headers()
                )
                if res.status_code == 200:
                    return res.json()
                logger.error("Erro ao solicitar QR Code: %s %s", res.status_code, res.text)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Falha ao gerar QR Code no provedor."
                )
        except httpx.RequestError as exc:
            logger.error("Falha de conexão com a Evolution API: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Provedor WhatsApp temporariamente inacessível."
            )

    async def get_connection_state(
        self,
        instance_name: str
    ) -> Dict[str, Any]:
        if self.mock_mode:
            inst = self._mock_instances.get(instance_name, {})
            state = inst.get("state", "close")
            return {
                "instance": {
                    "instanceName": instance_name,
                    "state": state
                }
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"{self.base_url}/instance/connectionState/{instance_name}",
                    headers=self._headers()
                )
                if res.status_code == 200:
                    return res.json()
                elif res.status_code == 404:
                    return {"instance": {"instanceName": instance_name, "state": "not_found"}}
                logger.error("Erro ao consultar estado da instância: %s %s", res.status_code, res.text)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Falha ao consultar estado da conexão no provedor."
                )
        except httpx.RequestError as exc:
            logger.error("Falha de conexão com a Evolution API: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Provedor WhatsApp temporariamente inacessível."
            )

    async def disconnect(
        self,
        instance_name: str
    ) -> Dict[str, Any]:
        if self.mock_mode:
            if instance_name in self._mock_instances:
                self._mock_instances[instance_name]["state"] = "close"
            return {"status": "SUCCESS", "response": {"message": "Instance logged out"}}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.delete(
                    f"{self.base_url}/instance/logout/{instance_name}",
                    headers=self._headers()
                )
                if res.status_code in (200, 204):
                    return res.json() if res.content else {"status": "SUCCESS"}
                return {"status": "SUCCESS", "detail": res.text}
        except httpx.RequestError as exc:
            logger.error("Falha de conexão ao desconectar: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Provedor WhatsApp temporariamente inacessível."
            )

    async def delete_instance(
        self,
        instance_name: str
    ) -> Dict[str, Any]:
        if self.mock_mode:
            self._mock_instances.pop(instance_name, None)
            return {"status": "SUCCESS", "response": {"message": "Instance deleted"}}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.delete(
                    f"{self.base_url}/instance/delete/{instance_name}",
                    headers=self._headers()
                )
                if res.status_code in (200, 204):
                    return res.json() if res.content else {"status": "SUCCESS"}
                return {"status": "SUCCESS", "detail": res.text}
        except httpx.RequestError as exc:
            logger.error("Falha de conexão ao deletar instância: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Provedor WhatsApp temporariamente inacessível."
            )

    async def send_text_message(
        self,
        instance_name: str,
        recipient: str,
        text: str
    ) -> Dict[str, Any]:
        if self.mock_mode:
            return {"key": {"id": "mock_msg_123"}, "status": "PENDING"}

        payload = {
            "number": recipient,
            "text": text
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.base_url}/message/sendText/{instance_name}",
                    json=payload,
                    headers=self._headers()
                )
                if res.status_code in (200, 201):
                    return res.json()
                logger.error("Erro ao enviar mensagem: %s %s", res.status_code, res.text)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Falha ao despachar mensagem no provedor."
                )
        except httpx.RequestError as exc:
            logger.error("Falha de conexão ao enviar mensagem: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Provedor WhatsApp temporariamente inacessível."
            )
