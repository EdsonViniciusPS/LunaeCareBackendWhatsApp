from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.security import derive_webhook_key
from tests.helpers import auth


@pytest.mark.asyncio
async def test_automation_rules_crud_and_isolation(client: AsyncClient):
    headers_a = auth("clinica_auto_a")
    headers_b = auth("clinica_auto_b")

    # 1. Cria conexão para a clínica A
    conn_a = await client.post("/api/v1/whatsapp/connections", headers=headers_a, json={})
    conn_a_id = conn_a.json()["id"]

    # 2. Cria regra de automação para a clínica A
    create_payload = {
        "connection_id": conn_a_id,
        "event_trigger": "appointment_created",
        "template": "Olá {{patient_name}}, sua consulta com {{professional_name}} foi agendada para {{appointment_date}} às {{appointment_time}}.",
        "enabled": 1,
        "settings": {"auto_confirm": True}
    }
    res = await client.post("/api/v1/whatsapp/automations", headers=headers_a, json=create_payload)
    assert res.status_code == 201
    rule_data = res.json()
    rule_id = rule_data["id"]
    assert rule_data["clinic_id"] == "clinica_auto_a"
    assert rule_data["event_trigger"] == "appointment_created"

    # 3. Lista regras da clínica A
    list_res = await client.get("/api/v1/whatsapp/automations", headers=headers_a)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1
    assert list_res.json()[0]["id"] == rule_id

    # 4. Clínica B não enxerga a regra da clínica A
    list_b = await client.get("/api/v1/whatsapp/automations", headers=headers_b)
    assert len(list_b.json()) == 0

    # 5. Clínica B tenta acessar/modificar regra da clínica A -> 404
    get_forbidden = await client.get(f"/api/v1/whatsapp/automations/{rule_id}", headers=headers_b)
    assert get_forbidden.status_code == 404

    # 6. Atualiza regra
    update_res = await client.put(
        f"/api/v1/whatsapp/automations/{rule_id}",
        headers=headers_a,
        json={"template": "Template atualizado: consulta em {{appointment_date}}"}
    )
    assert update_res.status_code == 200
    assert "Template atualizado" in update_res.json()["template"]

    # 7. Exclui regra
    del_res = await client.delete(f"/api/v1/whatsapp/automations/{rule_id}", headers=headers_a)
    assert del_res.status_code == 204

    # Verifica exclusão
    get_deleted = await client.get(f"/api/v1/whatsapp/automations/{rule_id}", headers=headers_a)
    assert get_deleted.status_code == 404


@pytest.mark.asyncio
async def test_pause_and_resume_all_automations(client: AsyncClient):
    headers = auth("clinica_pause")
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    conn_id = conn_res.json()["id"]

    # Cria 2 regras
    await client.post(
        "/api/v1/whatsapp/automations",
        headers=headers,
        json={
            "connection_id": conn_id,
            "event_trigger": "appointment_created",
            "template": "Criada",
            "enabled": 1
        }
    )
    await client.post(
        "/api/v1/whatsapp/automations",
        headers=headers,
        json={
            "connection_id": conn_id,
            "event_trigger": "appointment_reminder_24h",
            "template": "Lembrete",
            "enabled": 1
        }
    )

    # Pausa todas as automações da clínica
    pause_res = await client.post(
        "/api/v1/whatsapp/automations/pause",
        headers=headers,
        json={"enabled": False}
    )
    assert pause_res.status_code == 200
    assert pause_res.json()["action"] == "pausadas"
    assert pause_res.json()["affected_rules"] == 2

    # Verifica que todas as regras agora estão desativadas
    rules = (await client.get("/api/v1/whatsapp/automations", headers=headers)).json()
    assert all(r["enabled"] == 0 for r in rules)

    # Reativa todas as automações
    resume_res = await client.post(
        "/api/v1/whatsapp/automations/pause",
        headers=headers,
        json={"enabled": True}
    )
    assert resume_res.status_code == 200
    assert resume_res.json()["action"] == "reativadas"

    rules2 = (await client.get("/api/v1/whatsapp/automations", headers=headers)).json()
    assert all(r["enabled"] == 1 for r in rules2)


@pytest.mark.asyncio
async def test_agenda_event_appointment_flow(client: AsyncClient):
    headers = auth("clinica_agenda")

    # 1. Conecta WhatsApp
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    conn_id = conn_res.json()["id"]
    inst_name = conn_res.json()["provider_instance_id"]
    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{derive_webhook_key(inst_name)}",
        json={"event": "connection.update", "instance": inst_name, "data": {"state": "open"}}
    )

    # 2. Cria regra de confirmação imediata
    await client.post(
        "/api/v1/whatsapp/automations",
        headers=headers,
        json={
            "connection_id": conn_id,
            "event_trigger": "appointment_created",
            "template": "Olá {{patient_name}}, sua consulta com {{professional_name}} está confirmada para {{appointment_date}} às {{appointment_time}}."
        }
    )

    # 3. Cria regra de lembrete 24h antes
    await client.post(
        "/api/v1/whatsapp/automations",
        headers=headers,
        json={
            "connection_id": conn_id,
            "event_trigger": "appointment_reminder_24h",
            "template": "Lembrete: sua consulta com {{professional_name}} é amanhã às {{appointment_time}}.",
            "settings": {"hours_before": 24}
        }
    )

    # 4. Envia evento appointment.created para daqui a 3 dias
    future_date = datetime.now(timezone.utc) + timedelta(days=3)
    event_payload = {
        "event": "appointment.created",
        "appointment_id": "apt_123456",
        "patient_name": "Carlos Eduardo",
        "phone_number": "5511999991234",
        "professional_name": "Dr. Fernando",
        "appointment_datetime": future_date.isoformat()
    }

    event_res = await client.post(
        "/api/v1/whatsapp/automations/agenda-events",
        headers=headers,
        json=event_payload
    )
    assert event_res.status_code == 200
    assert event_res.json()["status"] == "processed"
    assert event_res.json()["scheduled_reminder_job_id"] is not None

    # 5. Verifica se mensagem imediata de confirmação foi enviada
    convs_res = await client.get("/api/v1/whatsapp/conversations", headers=headers)
    assert convs_res.status_code == 200
    conv_id = convs_res.json()[0]["id"]

    msgs_res = await client.get(
        f"/api/v1/whatsapp/conversations/{conv_id}/messages",
        headers=headers
    )
    first_msg = msgs_res.json()[0]
    assert "Carlos Eduardo" in first_msg["content"]
    assert "Dr. Fernando" in first_msg["content"]

    # 6. Reagenda consulta (appointment.rescheduled)
    new_date = datetime.now(timezone.utc) + timedelta(days=5)
    resched_res = await client.post(
        "/api/v1/whatsapp/automations/agenda-events",
        headers=headers,
        json={
            "event": "appointment.rescheduled",
            "appointment_id": "apt_123456",
            "patient_name": "Carlos Eduardo",
            "phone_number": "5511999991234",
            "professional_name": "Dr. Fernando",
            "appointment_datetime": new_date.isoformat()
        }
    )
    assert resched_res.status_code == 200

    # 7. Cancela consulta (appointment.cancelled)
    cancel_res = await client.post(
        "/api/v1/whatsapp/automations/agenda-events",
        headers=headers,
        json={
            "event": "appointment.cancelled",
            "appointment_id": "apt_123456",
            "patient_name": "Carlos Eduardo",
            "phone_number": "5511999991234",
            "professional_name": "Dr. Fernando",
            "appointment_datetime": new_date.isoformat()
        }
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"
    assert cancel_res.json()["jobs_cancelled"] >= 1


@pytest.mark.asyncio
async def test_due_jobs_processing_and_opt_out(client: AsyncClient):
    headers = auth("clinica_optout")

    # Conecta instância
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    conn_id = conn_res.json()["id"]
    inst_name = conn_res.json()["provider_instance_id"]
    webhook_key = derive_webhook_key(inst_name)
    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json={"event": "connection.update", "instance": inst_name, "data": {"state": "open"}}
    )

    # 1. Cria regra de lembrete
    await client.post(
        "/api/v1/whatsapp/automations",
        headers=headers,
        json={
            "connection_id": conn_id,
            "event_trigger": "appointment_reminder_24h",
            "template": "Olá {{patient_name}}, lembrete da sua consulta hoje às {{appointment_time}}.",
            "settings": {"hours_before": 2}
        }
    )

    # 2. Agenda consulta com data próxima (lembrete cai no passado, logo está 'due')
    past_reminder_date = datetime.now(timezone.utc) + timedelta(hours=1)
    await client.post(
        "/api/v1/whatsapp/automations/agenda-events",
        headers=headers,
        json={
            "event": "appointment.created",
            "appointment_id": "apt_due_001",
            "patient_name": "Renata Santos",
            "phone_number": "5511988881111",
            "professional_name": "Dra. Beatriz",
            "appointment_datetime": past_reminder_date.isoformat()
        }
    )

    # 3. Paciente envia comando de opt-out ("PARAR") via WhatsApp
    optout_webhook = {
        "event": "messages.upsert",
        "instance": inst_name,
        "data": {
            "key": {
                "remoteJid": "5511988881111@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG_OPTOUT_001"
            },
            "pushName": "Renata Santos",
            "message": {
                "conversation": "PARAR"
            }
        }
    }
    optout_res = await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json=optout_webhook
    )
    assert optout_res.status_code == 200

    # Verifica se resposta automática de opt-out foi registrada no histórico
    convs = (await client.get("/api/v1/whatsapp/conversations", headers=headers)).json()
    conv_id = convs[0]["id"]
    msgs = (await client.get(f"/api/v1/whatsapp/conversations/{conv_id}/messages", headers=headers)).json()
    # Última mensagem deve ser a confirmação de opt-out
    assert any("não receberá mais lembretes" in m["content"] for m in msgs)

    # 4. Executa processamento de jobs pendentes
    process_res = await client.post(
        "/api/v1/whatsapp/automations/process-due-jobs",
        headers=headers
    )
    assert process_res.status_code == 200
    # Nenhum lembrete novo para Renata deve ter sido enviado após o opt-out
    results = process_res.json()["results"]
    for r in results:
        if r.get("reason") == "opt_out":
            assert r["status"] == "cancelled"

    # 5. Paciente envia "COMEÇAR" para reativar
    optin_webhook = {
        "event": "messages.upsert",
        "instance": inst_name,
        "data": {
            "key": {
                "remoteJid": "5511988881111@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG_OPTIN_001"
            },
            "pushName": "Renata Santos",
            "message": {
                "conversation": "COMEÇAR"
            }
        }
    }
    optin_res = await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json=optin_webhook
    )
    assert optin_res.status_code == 200

    # Verifica confirmação de opt-in
    msgs_after = (await client.get(f"/api/v1/whatsapp/conversations/{conv_id}/messages", headers=headers)).json()
    assert any("reativados com sucesso" in m["content"] for m in msgs_after)


@pytest.mark.asyncio
async def test_agenda_event_formatted_phone_and_opt_out(client: AsyncClient):
    headers = auth("clinica_formatted_phone")

    # 1. Conecta instância
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers, json={})
    conn_id = conn_res.json()["id"]
    inst_name = conn_res.json()["provider_instance_id"]
    webhook_key = derive_webhook_key(inst_name)
    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json={"event": "connection.update", "instance": inst_name, "data": {"state": "open"}}
    )

    # 2. Cria regras de confirmação e lembrete
    await client.post(
        "/api/v1/whatsapp/automations",
        headers=headers,
        json={
            "connection_id": conn_id,
            "event_trigger": "appointment_created",
            "template": "Consulta criada para {{patient_name}}."
        }
    )
    await client.post(
        "/api/v1/whatsapp/automations",
        headers=headers,
        json={
            "connection_id": conn_id,
            "event_trigger": "appointment_reminder_24h",
            "template": "Lembrete: consulta hoje.",
            "settings": {"hours_before": 2}
        }
    )

    # 3. Agenda consulta enviando telefone com formatação (+55 (11) 97777-6666)
    near_time = datetime.now(timezone.utc) + timedelta(hours=1)
    event_res = await client.post(
        "/api/v1/whatsapp/automations/agenda-events",
        headers=headers,
        json={
            "event": "appointment.created",
            "appointment_id": "apt_fmt_001",
            "patient_name": "Juliana Lima",
            "phone_number": "+55 (11) 97777-6666",
            "professional_name": "Dr. Sergio",
            "appointment_datetime": near_time.isoformat()
        }
    )
    assert event_res.status_code == 200

    # 4. Verifica se a conversa e o contato foram criados com o telefone devidamente normalizado
    convs = (await client.get("/api/v1/whatsapp/conversations", headers=headers)).json()
    assert len(convs) == 1
    assert convs[0]["contact"]["phone_number"] == "5511977776666"

    # 5. Paciente envia opt-out ("PARAR") via WhatsApp
    optout_webhook = {
        "event": "messages.upsert",
        "instance": inst_name,
        "data": {
            "key": {
                "remoteJid": "5511977776666@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG_OPTOUT_FMT_001"
            },
            "pushName": "Juliana Lima",
            "message": {
                "conversation": "PARAR"
            }
        }
    }
    optout_res = await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{webhook_key}",
        json=optout_webhook
    )
    assert optout_res.status_code == 200

    # 6. Executa processamento de jobs pendentes
    # O job deve ter sido cancelado pelo opt-out imediatamente e não deve enviar lembrete
    process_res = await client.post(
        "/api/v1/whatsapp/automations/process-due-jobs",
        headers=headers
    )
    assert process_res.status_code == 200
    # Verifica que não há novos disparos de lembrete
    conv_id = convs[0]["id"]
    msgs = (await client.get(f"/api/v1/whatsapp/conversations/{conv_id}/messages", headers=headers)).json()
    assert not any("Lembrete: consulta hoje." in m["content"] for m in msgs)


@pytest.mark.asyncio
async def test_process_due_jobs_security_and_scoping(client: AsyncClient):
    # 1. Requisição sem cabeçalhos de autenticação -> 401
    unauth_res = await client.post("/api/v1/whatsapp/automations/process-due-jobs")
    assert unauth_res.status_code == 401

    # 2. Requisição com token interno inválido -> 401
    bad_token_res = await client.post(
        "/api/v1/whatsapp/automations/process-due-jobs",
        headers={"X-Internal-Token": "chave_incorreta_123"}
    )
    assert bad_token_res.status_code == 401

    # 3. Cria conexões e regras para Clínica A e Clínica B
    headers_a = auth("clinica_scoping_a")
    headers_b = auth("clinica_scoping_b")

    conn_a = (await client.post("/api/v1/whatsapp/connections", headers=headers_a, json={})).json()
    conn_b = (await client.post("/api/v1/whatsapp/connections", headers=headers_b, json={})).json()

    # Ativa conexões
    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{derive_webhook_key(conn_a['provider_instance_id'])}",
        json={"event": "connection.update", "instance": conn_a["provider_instance_id"], "data": {"state": "open"}}
    )
    await client.post(
        f"/api/v1/whatsapp/webhooks/evolution/{derive_webhook_key(conn_b['provider_instance_id'])}",
        json={"event": "connection.update", "instance": conn_b["provider_instance_id"], "data": {"state": "open"}}
    )

    # Regras de lembrete
    await client.post(
        "/api/v1/whatsapp/automations",
        headers=headers_a,
        json={"connection_id": conn_a["id"], "event_trigger": "appointment_reminder_24h", "template": "Lembrete A", "settings": {"hours_before": 2}}
    )
    await client.post(
        "/api/v1/whatsapp/automations",
        headers=headers_b,
        json={"connection_id": conn_b["id"], "event_trigger": "appointment_reminder_24h", "template": "Lembrete B", "settings": {"hours_before": 2}}
    )

    # Agenda lembretes pendentes para ambas
    near_time = datetime.now(timezone.utc) + timedelta(hours=1)
    await client.post(
        "/api/v1/whatsapp/automations/agenda-events",
        headers=headers_a,
        json={
            "event": "appointment.created",
            "appointment_id": "apt_scope_a",
            "patient_name": "Paciente A",
            "phone_number": "5511911110000",
            "professional_name": "Dr. A",
            "appointment_datetime": near_time.isoformat()
        }
    )
    await client.post(
        "/api/v1/whatsapp/automations/agenda-events",
        headers=headers_b,
        json={
            "event": "appointment.created",
            "appointment_id": "apt_scope_b",
            "patient_name": "Paciente B",
            "phone_number": "5511922220000",
            "professional_name": "Dr. B",
            "appointment_datetime": near_time.isoformat()
        }
    )

    # 4. Clínica A chama /process-due-jobs com seu próprio JWT Bearer
    # Deve processar APENAS o job da Clínica A, sem tocar no da Clínica B
    res_a = await client.post("/api/v1/whatsapp/automations/process-due-jobs", headers=headers_a)
    assert res_a.status_code == 200
    assert res_a.json()["clinic_id"] == "clinica_scoping_a"
    assert res_a.json()["processed_count"] == 1

    # Chamada subsequente pela Clínica A não tem mais jobs pendentes para ela
    res_a_again = await client.post("/api/v1/whatsapp/automations/process-due-jobs", headers=headers_a)
    assert res_a_again.status_code == 200
    assert res_a_again.json()["processed_count"] == 0

    # 5. Token interno do microsserviço processa o restante (Clínica B)
    res_internal = await client.post(
        "/api/v1/whatsapp/automations/process-due-jobs",
        headers={"X-Internal-Token": settings.INTERNAL_API_KEY}
    )
    assert res_internal.status_code == 200
    assert res_internal.json()["processed_count"] == 1


def test_due_jobs_scheduler_loop_execution():
    import threading
    from app.workers.main import run_due_jobs_scheduler_loop

    stop_event = threading.Event()
    stop_event.set()  # Encerra após o primeiro ciclo
    # Executa sem exceção
    run_due_jobs_scheduler_loop(interval_seconds=1, stop_event=stop_event)


