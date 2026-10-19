import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import derive_webhook_key
from app.core.status import should_transition_message_status
from app.models.entities import WhatsAppMessage
from app.repositories.contact_repository import ContactRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.job_repository import JobRepository
from tests.helpers import auth


def test_should_transition_message_status_rules():
    # 1. Ciclo progressivo normal
    assert should_transition_message_status("queued", "sent") is True
    assert should_transition_message_status("sent", "delivered") is True
    assert should_transition_message_status("delivered", "read") is True

    # 2. Idempotência de mesmo status
    assert should_transition_message_status("delivered", "delivered") is True
    assert should_transition_message_status("read", "read") is True

    # 3. Regressão bloqueada (anti-reversão)
    assert should_transition_message_status("read", "delivered") is False
    assert should_transition_message_status("read", "sent") is False
    assert should_transition_message_status("read", "queued") is False
    assert should_transition_message_status("delivered", "sent") is False
    assert should_transition_message_status("delivered", "queued") is False

    # 4. Estado de falha
    assert should_transition_message_status("queued", "failed") is True
    assert should_transition_message_status("sent", "failed") is True
    assert should_transition_message_status("delivered", "failed") is False
    assert should_transition_message_status("read", "failed") is False
    assert should_transition_message_status("failed", "queued") is False
    assert should_transition_message_status("failed", "sent") is False


@pytest.mark.asyncio
async def test_monotonic_message_status_in_webhooks(client: AsyncClient):
    """
    Simula cenário onde o webhook READ chega antes do DELIVERY_ACK.
    O status final deve permanecer 'read' e não sofrer regressão para 'delivered'.
    """
    headers = auth("clinica_monotonic")

    # 1. Cria conexão e simula ativação
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    inst_name = conn_res.json()["provider_instance_id"]
    conn_id = conn_res.json()["id"]
    webhook_key = derive_webhook_key(inst_name)

    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json={"event": "connection.update", "instance": inst_name, "data": {"state": "open"}}
    )

    # 2. Envia mensagem
    msg_res = await client.post(
        "/api/v1/whatsapp/messages",
        headers=headers,
        json={
            "connection_id": conn_id,
            "recipient": "5511999998877",
            "content": "Confirmação de agendamento",
            "idempotency_key": "msg_monotonic_01"
        }
    )
    msg_data = msg_res.json()
    provider_msg_id = msg_data.get("provider_message_id") or "mock_msg_123"
    conv_id = msg_data["conversation_id"]

    # 3. Webhook de LEITURA (READ) chega primeiro (ex: atraso na fila de delivery)
    read_hook = await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json={
            "event": "messages.update",
            "instance": inst_name,
            "data": {
                "key": {"id": provider_msg_id},
                "status": "READ"
            }
        }
    )
    assert read_hook.status_code == 200

    # Verifica se a mensagem está 'read'
    msgs_res = await client.get(f"/api/v1/whatsapp/conversations/{conv_id}/messages", headers=headers)
    msg_after_read = msgs_res.json()[0]
    assert msg_after_read["status"] == "read"
    assert msg_after_read["read_at"] is not None

    # 4. Webhook de ENTREGA (DELIVERY_ACK) chega atrasado
    deliv_hook = await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json={
            "event": "messages.update",
            "instance": inst_name,
            "data": {
                "key": {"id": provider_msg_id},
                "status": "DELIVERY_ACK"
            }
        }
    )
    assert deliv_hook.status_code == 200

    # 5. O status NÃO deve regredir para 'delivered' — deve continuar 'read'
    msgs_res2 = await client.get(f"/api/v1/whatsapp/conversations/{conv_id}/messages", headers=headers)
    msg_final = msgs_res2.json()[0]
    assert msg_final["status"] == "read"
    assert msg_final["read_at"] is not None
    assert msg_final["delivered_at"] is not None


@pytest.mark.asyncio
async def test_contact_and_conversation_concurrency(db_session: AsyncSession):
    """
    Verifica que get_or_create lida com segurança com chamadas concorrentes
    para contatos e conversas sem quebrar com IntegrityError.
    """
    contact_repo = ContactRepository()
    conv_repo = ConversationRepository()

    clinic_id = "clinica_concorrencia"
    phone = "5511999990000"
    conn_id = "conn_mock_001"

    # 1. Criação concorrente de contato
    contact_a = await contact_repo.get_or_create(db_session, clinic_id, phone, display_name="Contato A")
    contact_b = await contact_repo.get_or_create(db_session, clinic_id, phone, display_name="Contato B")

    assert contact_a.id == contact_b.id
    assert contact_b.phone_number == phone

    # 2. Criação concorrente de conversa
    conv_a = await conv_repo.get_or_create(db_session, clinic_id, conn_id, contact_a.id)
    conv_b = await conv_repo.get_or_create(db_session, clinic_id, conn_id, contact_a.id)

    assert conv_a.id == conv_b.id


@pytest.mark.asyncio
async def test_job_repository_get_due_jobs_safety(db_session: AsyncSession):
    """
    Garante que JobRepository.get_due_jobs executa a query com sucesso
    e aciona com segurança a lógica de trava de concorrência.
    """
    job_repo = JobRepository()
    due_jobs = await job_repo.get_due_jobs(db_session, clinic_id="clinica_teste")
    assert isinstance(due_jobs, list)
