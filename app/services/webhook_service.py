import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import normalize_phone
from app.core.security import verify_webhook_key
from app.models.connection import ConnectionStatus, WhatsAppConnection
from app.models.entities import WhatsAppMessage
from app.repositories.connection_repository import ConnectionRepository
from app.repositories.contact_repository import ContactRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.webhook_event_repository import WebhookEventRepository
from app.services.consent_service import ConsentService
from app.providers import get_whatsapp_provider
from app.providers.base import WhatsAppProvider

logger = logging.getLogger(__name__)


def _extract_instance_name(payload: Dict[str, Any]) -> Optional[str]:
    inst = payload.get("instance")
    if isinstance(inst, str):
        return inst
    if isinstance(inst, dict):
        return inst.get("instanceName")
    return payload.get("instanceName")


def _extract_text_content(msg: Dict[str, Any]) -> str:
    if not isinstance(msg, dict):
        return ""
    if "conversation" in msg and isinstance(msg["conversation"], str):
        return msg["conversation"]
    extended = msg.get("extendedTextMessage")
    if isinstance(extended, dict) and "text" in extended:
        return str(extended["text"])
    return ""


def _sanitize_audit_payload(full_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Minimiza os dados armazenados na tabela de auditoria técnica (LGPD).
    Preserva metadados de protocolo para deduplicação e diagnóstico técnico,
    removendo textos de saúde sensíveis que já residem de forma controlada em whatsapp_messages.
    """
    if not isinstance(full_payload, dict):
        return {}

    sanitized: Dict[str, Any] = {
        "event": full_payload.get("event"),
        "instance": full_payload.get("instance"),
        "date_time": full_payload.get("date_time"),
    }
    data = full_payload.get("data")
    if isinstance(data, dict):
        key = data.get("key") or {}
        sanitized["data"] = {
            "key": {
                "id": key.get("id"),
                "fromMe": key.get("fromMe"),
                "remoteJid": key.get("remoteJid"),
            },
            "status": data.get("status") or data.get("state"),
            "pushName": data.get("pushName"),
            "messageType": data.get("messageType") or (list(data.get("message", {}).keys()) if isinstance(data.get("message"), dict) else None),
            "messageTimestamp": data.get("messageTimestamp"),
        }
    elif isinstance(data, list):
        sanitized["data"] = [
            {
                "key": (it.get("key") or {}) if isinstance(it, dict) else {},
                "status": it.get("status") if isinstance(it, dict) else None,
                "messageType": it.get("messageType") if isinstance(it, dict) else None,
            }
            for it in data if isinstance(it, dict)
        ]
    return sanitized


class WebhookService:
    def __init__(
        self,
        connection_repo: ConnectionRepository,
        event_repo: Optional[WebhookEventRepository] = None,
        contact_repo: Optional[ContactRepository] = None,
        conversation_repo: Optional[ConversationRepository] = None,
        message_repo: Optional[MessageRepository] = None,
        consent_service: Optional[ConsentService] = None,
        provider: Optional[WhatsAppProvider] = None,
    ):
        self.connection_repo = connection_repo
        self.event_repo = event_repo or WebhookEventRepository()
        self.contact_repo = contact_repo or ContactRepository()
        self.conversation_repo = conversation_repo or ConversationRepository()
        self.message_repo = message_repo or MessageRepository()
        self.consent_service = consent_service or ConsentService()
        self.provider = provider

    async def handle_evolution_event(
        self, db: AsyncSession, provider_key: str, payload: Dict[str, Any]
    ) -> bool:
        """
        Retorna False se o webhook não for autêntico (instância desconhecida ou
        chave HMAC inválida).
        """
        instance_name = _extract_instance_name(payload)
        if not instance_name or not verify_webhook_key(instance_name, provider_key):
            return False

        connection = await self.connection_repo.get_by_instance_id(db, instance_name)
        if connection is None:
            return False

        raw_event = str(payload.get("event", "")).upper().replace(".", "_")
        data = payload.get("data") or {}

        # 1. Tratamento de CONNECTION_UPDATE
        if raw_event == "CONNECTION_UPDATE":
            await self._handle_connection_update(db, connection, data)
            return True

        # 2. Tratamento de mensagens recebidas (MESSAGES_UPSERT)
        if raw_event in ("MESSAGES_UPSERT", "MESSAGE_UPSERT"):
            await self._handle_messages_upsert(db, connection, raw_event, data, payload)
            return True

        # 3. Tratamento de atualizações de status de mensagem (MESSAGES_UPDATE)
        if raw_event in ("MESSAGES_UPDATE", "MESSAGE_UPDATE"):
            await self._handle_messages_update(db, connection, raw_event, data, payload)
            return True

        # Outros eventos registrados para observabilidade
        event_key = f"evolution_{connection.id}_{raw_event}_{uuid.uuid4().hex[:12]}"
        await self.event_repo.record_event(
            db, connection.id, raw_event, event_key, {"event": raw_event}
        )
        return True

    async def _handle_connection_update(
        self, db: AsyncSession, connection: WhatsAppConnection, data: Dict[str, Any]
    ):
        state = str(data.get("state", "")).lower()
        if state == "open" and connection.status != ConnectionStatus.CONNECTED.value:
            connection.status = ConnectionStatus.CONNECTED.value
            connection.connected_at = datetime.now(timezone.utc)
            await self.connection_repo.update(db, connection)
        elif state in ("close", "refused") and connection.status in (
            ConnectionStatus.CONNECTED.value,
            ConnectionStatus.CONNECTING.value,
        ):
            connection.status = ConnectionStatus.DISCONNECTED.value
            await self.connection_repo.update(db, connection)

    async def _handle_messages_upsert(
        self,
        db: AsyncSession,
        connection: WhatsAppConnection,
        event_type: str,
        data: Any,
        full_payload: Dict[str, Any]
    ):
        items: List[Dict[str, Any]] = [data] if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for item in items:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or {}
            remote_jid = str(key.get("remoteJid", ""))
            from_me = bool(key.get("fromMe", False))
            provider_msg_id = key.get("id")

            if not provider_msg_id or not remote_jid:
                continue

            # Ignora mensagens de grupo (ex: @g.us)
            if remote_jid.endswith("@g.us"):
                continue

            event_key = f"evolution_upsert_{connection.id}_{provider_msg_id}"
            _, is_new = await self.event_repo.record_event(
                db, connection.id, event_type, event_key, _sanitize_audit_payload(full_payload)
            )
            if not is_new:
                logger.info("Evento duplicado ignorado (idempotência): %s", event_key)
                continue

            # Apenas mensagens enviadas pelo paciente/contato (inbound) criam conversa/mensagem
            if not from_me:
                clean_phone = normalize_phone(remote_jid)
                push_name = item.get("pushName")
                text_content = _extract_text_content(item.get("message") or {})

                contact = await self.contact_repo.get_or_create(
                    db,
                    clinic_id=connection.clinic_id,
                    phone_number=clean_phone,
                    display_name=push_name
                )
                conversation = await self.conversation_repo.get_or_create(
                    db,
                    clinic_id=connection.clinic_id,
                    connection_id=connection.id,
                    contact_id=contact.id
                )

                now = datetime.now(timezone.utc)
                message = WhatsAppMessage(
                    id=str(uuid.uuid4()),
                    clinic_id=connection.clinic_id,
                    connection_id=connection.id,
                    conversation_id=conversation.id,
                    provider_message_id=provider_msg_id,
                    direction="inbound",
                    type="text",
                    content=text_content,
                    status="received",
                    created_at=now
                )
                await self.message_repo.create(db, message)
                await self.conversation_repo.update_last_message(db, conversation, now)
                logger.info("Nova mensagem recebida (%s) na conversa %s", provider_msg_id, conversation.id)

                # Detecta comandos de consentimento/opt-out (LGPD)
                is_consent, reply_text = await self.consent_service.handle_inbound_message(
                    db, clinic_id=connection.clinic_id, contact=contact, text=text_content
                )
                if is_consent and reply_text:
                    try:
                        prov = self.provider or get_whatsapp_provider()
                        await prov.send_text_message(
                            instance_name=connection.provider_instance_id,
                            recipient=clean_phone,
                            text=reply_text
                        )
                        reply_msg = WhatsAppMessage(
                            id=str(uuid.uuid4()),
                            clinic_id=connection.clinic_id,
                            connection_id=connection.id,
                            conversation_id=conversation.id,
                            direction="outbound",
                            type="text",
                            content=reply_text,
                            status="sent",
                            created_at=datetime.now(timezone.utc),
                            sent_at=datetime.now(timezone.utc)
                        )
                        await self.message_repo.create(db, reply_msg)
                        logger.info("Resposta automática de consentimento enviada para %s", clean_phone)
                    except Exception as exc:
                        logger.error("Erro ao enviar resposta automática de consentimento: %s", exc)

    async def _handle_messages_update(
        self,
        db: AsyncSession,
        connection: WhatsAppConnection,
        event_type: str,
        data: Any,
        full_payload: Dict[str, Any]
    ):
        items: List[Dict[str, Any]] = [data] if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for item in items:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or {}
            provider_msg_id = key.get("id") or item.get("id")
            raw_status = str(item.get("status") or item.get("update", {}).get("status", "")).upper()

            if not provider_msg_id or not raw_status:
                continue

            event_key = f"evolution_update_{connection.id}_{provider_msg_id}_{raw_status}"
            _, is_new = await self.event_repo.record_event(
                db, connection.id, event_type, event_key, _sanitize_audit_payload(full_payload)
            )
            if not is_new:
                continue

            message = await self.message_repo.get_by_provider_message_id(db, str(provider_msg_id))
            if message:
                now = datetime.now(timezone.utc)
                if raw_status in ("DELIVERY_ACK", "DELIVERED"):
                    if not message.delivered_at:
                        message.delivered_at = now
                    if message.transition_status_to("delivered"):
                        logger.info("Mensagem %s marcada como entregue.", message.id)
                    else:
                        logger.info("Ignorando regressão de status para mensagem %s (atual: %s, recebido: %s)", message.id, message.status, raw_status)
                    await self.message_repo.update(db, message)
                elif raw_status in ("READ", "PLAYED"):
                    if not message.delivered_at:
                        message.delivered_at = now
                    message.read_at = now
                    if message.transition_status_to("read"):
                        logger.info("Mensagem %s marcada como lida.", message.id)
                    await self.message_repo.update(db, message)
                elif raw_status in ("ERROR", "FAILED"):
                    if message.transition_status_to("failed"):
                        logger.info("Mensagem %s marcada como falha.", message.id)
                    await self.message_repo.update(db, message)
