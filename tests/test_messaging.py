import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import derive_webhook_key
from tests.helpers import auth


@pytest.mark.asyncio
async def test_send_message_requires_connected_state(client: AsyncClient):
    # 1. Cria conexão (fica em pending)
    res_conn = await client.post(
        "/api/v1/whatsapp/connections",
        headers=auth("clinica_test"),
        json={}
    )
    assert res_conn.status_code == 201
    conn_id = res_conn.json()["id"]

    # 2. Tenta enviar mensagem com status pending
    res = await client.post(
        "/api/v1/whatsapp/messages",
        headers=auth("clinica_test"),
        json={
            "connection_id": conn_id,
            "recipient": "5511999998888",
            "content": "Olá!"
        }
    )
    assert res.status_code == 400
    assert "não está ativa" in res.json()["detail"]


@pytest.mark.asyncio
async def test_send_message_success_and_flow(client: AsyncClient):
    headers = auth("clinica_a")

    # 1. Cria conexão e simula conexão ativa
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    conn_id = conn_res.json()["id"]
    instance_id = conn_res.json()["provider_instance_id"]
    webhook_key = derive_webhook_key(instance_id)

    # Simula evento webhook de conexão conectada
    hook_res = await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json={
            "event": "connection.update",
            "instance": instance_id,
            "data": {"state": "open"}
        }
    )
    assert hook_res.status_code == 200

    # 2. Envia mensagem
    msg_res = await client.post(
        "/api/v1/whatsapp/messages",
        headers=headers,
        json={
            "connection_id": conn_id,
            "recipient": "+55 (11) 99999-8888",
            "content": "Sua consulta com a Dra. Ana está confirmada.",
            "idempotency_key": "msg_key_001"
        }
    )
    assert msg_res.status_code == 201
    msg_data = msg_res.json()
    assert msg_data["clinic_id"] == "clinica_a"
    assert msg_data["direction"] == "outbound"
    assert msg_data["content"] == "Sua consulta com a Dra. Ana está confirmada."
    assert msg_data["status"] in ("sent", "queued")
    assert msg_data["idempotency_key"] == "msg_key_001"
    conversation_id = msg_data["conversation_id"]

    # 3. Consulta conversas da clínica
    convs_res = await client.get("/api/v1/whatsapp/conversations", headers=headers)
    assert convs_res.status_code == 200
    convs = convs_res.json()
    assert len(convs) == 1
    assert convs[0]["id"] == conversation_id
    assert convs[0]["contact"]["phone_number"] == "5511999998888"

    # 4. Consulta mensagens da conversa
    msgs_res = await client.get(
        f"/api/v1/whatsapp/conversations/{conversation_id}/messages",
        headers=headers
    )
    assert msgs_res.status_code == 200
    msgs = msgs_res.json()
    assert len(msgs) == 1
    assert msgs[0]["id"] == msg_data["id"]


@pytest.mark.asyncio
async def test_send_message_idempotency(client: AsyncClient):
    headers = auth("clinica_idemp")

    # Cria e ativa conexão
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    conn_id = conn_res.json()["id"]
    instance_id = conn_res.json()["provider_instance_id"]
    webhook_key = derive_webhook_key(instance_id)

    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json={"event": "connection.update", "instance": instance_id, "data": {"state": "open"}}
    )

    payload = {
        "connection_id": conn_id,
        "recipient": "5511999997777",
        "content": "Mensagem com chave de idempotência",
    }
    custom_headers = {**headers, "X-Idempotency-Key": "req_unique_12345"}

    # Primeiro envio
    res1 = await client.post("/api/v1/whatsapp/messages", headers=custom_headers, json=payload)
    assert res1.status_code == 201
    msg1_id = res1.json()["id"]

    # Segundo envio com o mesmo X-Idempotency-Key
    res2 = await client.post("/api/v1/whatsapp/messages", headers=custom_headers, json=payload)
    assert res2.status_code in (200, 201)
    assert res2.json()["id"] == msg1_id

    # Verifica que só existe 1 mensagem na conversa
    conv_id = res1.json()["conversation_id"]
    msgs_res = await client.get(
        f"/api/v1/whatsapp/conversations/{conv_id}/messages",
        headers=headers
    )
    assert len(msgs_res.json()) == 1


@pytest.mark.asyncio
async def test_multi_tenant_isolation_conversations_and_messages(client: AsyncClient):
    headers_a = auth("clinica_alfa")
    headers_b = auth("clinica_beta")

    # Conexão Clínica Alfa
    res_a = await client.post("/api/v1/whatsapp/connections", headers=headers_a, json={})
    conn_a_id = res_a.json()["id"]
    inst_a = res_a.json()["provider_instance_id"]
    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{derive_webhook_key(inst_a)}",
        json={"event": "connection.update", "instance": inst_a, "data": {"state": "open"}}
    )

    # Conexão Clínica Beta
    res_b = await client.post("/api/v1/whatsapp/connections", headers=headers_b, json={})
    conn_b_id = res_b.json()["id"]
    inst_b = res_b.json()["provider_instance_id"]
    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{derive_webhook_key(inst_b)}",
        json={"event": "connection.update", "instance": inst_b, "data": {"state": "open"}}
    )

    # Clínica Beta tenta usar conexão da Clínica Alfa -> 404
    hijack_res = await client.post(
        "/api/v1/whatsapp/messages",
        headers=headers_b,
        json={"connection_id": conn_a_id, "recipient": "5511999990000", "content": "Teste invasão"}
    )
    assert hijack_res.status_code == 404

    # Alfa envia mensagem
    msg_a = await client.post(
        "/api/v1/whatsapp/messages",
        headers=headers_a,
        json={"connection_id": conn_a_id, "recipient": "5511999991111", "content": "Msg Alfa"}
    )
    assert msg_a.status_code == 201
    conv_a_id = msg_a.json()["conversation_id"]

    # Beta consulta conversas -> vazia!
    convs_b = await client.get("/api/v1/whatsapp/conversations", headers=headers_b)
    assert len(convs_b.json()) == 0

    # Beta tenta ler mensagens da conversa de Alfa -> 404
    forbidden_msgs = await client.get(
        f"/api/v1/whatsapp/conversations/{conv_a_id}/messages",
        headers=headers_b
    )
    assert forbidden_msgs.status_code == 404


@pytest.mark.asyncio
async def test_webhook_inbound_messages_upsert_and_deduplication(client: AsyncClient):
    headers = auth("clinica_inbound")

    # Conecta instância
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    inst_name = conn_res.json()["provider_instance_id"]
    webhook_key = derive_webhook_key(inst_name)

    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json={"event": "connection.update", "instance": inst_name, "data": {"state": "open"}}
    )

    upsert_payload = {
        "event": "messages.upsert",
        "instance": inst_name,
        "data": {
            "key": {
                "remoteJid": "5511988887777@s.whatsapp.net",
                "fromMe": False,
                "id": "PROV_MSG_INBOUND_001"
            },
            "pushName": "Paciente João",
            "message": {
                "conversation": "Olá, gostaria de confirmar o agendamento."
            }
        }
    }

    # 1. Envia webhook de mensagem recebida
    res = await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json=upsert_payload
    )
    assert res.status_code == 200
    assert res.json() == {"received": True}

    # 2. Re-envia o mesmo webhook (simulando retentativa do provedor) -> não duplica!
    res_dup = await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json=upsert_payload
    )
    assert res_dup.status_code == 200

    # 3. Verifica que a conversa e a mensagem foram criadas exatamente uma vez
    convs_res = await client.get("/api/v1/whatsapp/conversations", headers=headers)
    assert convs_res.status_code == 200
    convs = convs_res.json()
    assert len(convs) == 1
    assert convs[0]["contact"]["phone_number"] == "5511988887777"
    assert convs[0]["contact"]["display_name"] == "Paciente João"

    conv_id = convs[0]["id"]
    msgs_res = await client.get(
        f"/api/v1/whatsapp/conversations/{conv_id}/messages",
        headers=headers
    )
    msgs = msgs_res.json()
    assert len(msgs) == 1
    assert msgs[0]["direction"] == "inbound"
    assert msgs[0]["content"] == "Olá, gostaria de confirmar o agendamento."
    assert msgs[0]["status"] == "received"


@pytest.mark.asyncio
async def test_webhook_messages_update_delivered_and_read(client: AsyncClient):
    headers = auth("clinica_receipts")

    # Conecta instância
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    inst_name = conn_res.json()["provider_instance_id"]
    conn_id = conn_res.json()["id"]
    webhook_key = derive_webhook_key(inst_name)

    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json={"event": "connection.update", "instance": inst_name, "data": {"state": "open"}}
    )

    # Envia mensagem que receberá provider_message_id
    msg_res = await client.post(
        "/api/v1/whatsapp/messages",
        headers=headers,
        json={
            "connection_id": conn_id,
            "recipient": "5511977776666",
            "content": "Lembrete de consulta"
        }
    )
    msg_data = msg_res.json()
    provider_msg_id = msg_data["provider_message_id"] or "mock_msg_123"

    # Webhook de entrega (DELIVERY_ACK)
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

    # Consulta mensagem atualizada
    conv_id = msg_data["conversation_id"]
    msgs_res = await client.get(
        f"/api/v1/whatsapp/conversations/{conv_id}/messages",
        headers=headers
    )
    updated_msg = msgs_res.json()[0]
    assert updated_msg["status"] == "delivered"
    assert updated_msg["delivered_at"] is not None

    # Webhook de leitura (READ)
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

    # Consulta mensagem atualizada para 'read'
    msgs_res2 = await client.get(
        f"/api/v1/whatsapp/conversations/{conv_id}/messages",
        headers=headers
    )
    read_msg = msgs_res2.json()[0]
    assert read_msg["status"] == "read"
    assert read_msg["read_at"] is not None


@pytest.mark.asyncio
async def test_invalid_phone_number_rejected(client: AsyncClient):
    headers = auth("clinica_val")
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    conn_id = conn_res.json()["id"]
    inst_name = conn_res.json()["provider_instance_id"]
    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{derive_webhook_key(inst_name)}",
        json={"event": "connection.update", "instance": inst_name, "data": {"state": "open"}}
    )

    # 1. Rejeição por tamanho mínimo no schema (< 8 caracteres)
    res_short = await client.post(
        "/api/v1/whatsapp/messages",
        headers=headers,
        json={"connection_id": conn_id, "recipient": "123", "content": "Olá"}
    )
    assert res_short.status_code == 422

    # 2. Rejeição por número incompleto na validação de negócio (< 10 dígitos)
    res = await client.post(
        "/api/v1/whatsapp/messages",
        headers=headers,
        json={"connection_id": conn_id, "recipient": "12345678", "content": "Olá"}
    )
    assert res.status_code == 422
    assert "Número de telefone inválido" in res.json()["detail"]


@pytest.mark.asyncio
async def test_pagination_conversations_and_messages(client: AsyncClient):
    headers = auth("clinica_pages")
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    conn_id = conn_res.json()["id"]
    inst_name = conn_res.json()["provider_instance_id"]
    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{derive_webhook_key(inst_name)}",
        json={"event": "connection.update", "instance": inst_name, "data": {"state": "open"}}
    )

    # Cria 3 conversas com envio para números diferentes
    for i in range(1, 4):
        await client.post(
            "/api/v1/whatsapp/messages",
            headers=headers,
            json={"connection_id": conn_id, "recipient": f"551190000000{i}", "content": f"Msg {i}"}
        )

    # Paginação: limit=2, skip=0
    res_page1 = await client.get("/api/v1/whatsapp/conversations?limit=2&skip=0", headers=headers)
    assert len(res_page1.json()) == 2

    # Paginação: limit=2, skip=2
    res_page2 = await client.get("/api/v1/whatsapp/conversations?limit=2&skip=2", headers=headers)
    assert len(res_page2.json()) == 1

