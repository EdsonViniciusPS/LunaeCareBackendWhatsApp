import pytest
from httpx import AsyncClient, Response
from fastapi import HTTPException

from app.providers.evolution import EvolutionProvider
from app.services.webhook_service import _sanitize_audit_payload
from tests.helpers import auth


def test_sanitize_audit_payload_removes_sensitive_clinical_text():
    raw_payload = {
        "event": "messages.upsert",
        "instance": "lunae_inst_123",
        "date_time": "2026-10-19T10:00:00Z",
        "data": {
            "key": {
                "remoteJid": "5511999998888@s.whatsapp.net",
                "fromMe": False,
                "id": "MSG_SENSITIVE_001"
            },
            "pushName": "Paciente Maria",
            "message": {
                "conversation": "Doutor, estou sentindo fortes dores no peito e tomei o remédio X."
            }
        }
    }

    sanitized = _sanitize_audit_payload(raw_payload)

    # Metadados de protocolo mantidos
    assert sanitized["event"] == "messages.upsert"
    assert sanitized["instance"] == "lunae_inst_123"
    assert sanitized["data"]["key"]["id"] == "MSG_SENSITIVE_001"
    assert sanitized["data"]["key"]["remoteJid"] == "5511999998888@s.whatsapp.net"
    assert sanitized["data"]["pushName"] == "Paciente Maria"

    # Conteúdo de saúde minimizado (removido do payload do webhook de auditoria)
    assert "Doutor, estou sentindo fortes dores" not in str(sanitized)
    assert "conversation" not in sanitized["data"].get("message", {})


@pytest.mark.asyncio
async def test_evolution_provider_v2_payload_structure(monkeypatch):
    """
    Verifica se create_instance envia o payload aninhado exigido pela Evolution API v2.
    """
    captured_requests = []

    async def mock_post(client_self, url, json=None, headers=None):
        captured_requests.append({"url": str(url), "json": json, "headers": headers})
        return Response(200, json={"instance": {"instanceName": "lunae_test", "status": "created"}})

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    provider = EvolutionProvider(
        base_url="http://evolution-mock:8080",
        api_key="test_api_key",
        mock_mode=False
    )

    result = await provider.create_instance(
        instance_name="lunae_test_instance",
        webhook_url="http://lunae:8000/api/v1/whatsapp/webhooks/evolution/key123"
    )

    assert result["instance"]["status"] == "created"
    assert len(captured_requests) == 1
    req_json = captured_requests[0]["json"]

    # Valida formato Evolution v2
    assert req_json["instanceName"] == "lunae_test_instance"
    assert req_json["integration"] == "WHATSAPP-BAILEYS"
    assert isinstance(req_json["webhook"], dict)
    assert req_json["webhook"]["url"] == "http://lunae:8000/api/v1/whatsapp/webhooks/evolution/key123"
    assert "CONNECTION_UPDATE" in req_json["webhook"]["events"]
    assert "MESSAGES_UPSERT" in req_json["webhook"]["events"]


@pytest.mark.asyncio
async def test_evolution_provider_error_message_sanitization(monkeypatch):
    """
    Garante que falhas da Evolution API não vazem respostas e dados brutos no detail HTTP 502.
    """
    async def mock_post_error(client_self, url, json=None, headers=None):
        return Response(500, text='{"internal_stacktrace": "crash at db:5432/evolution_secret_table"}')

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_error)

    provider = EvolutionProvider(
        base_url="http://evolution-mock:8080",
        api_key="test_api_key",
        mock_mode=False
    )

    with pytest.raises(HTTPException) as excinfo:
        await provider.create_instance(instance_name="lunae_failing_inst")

    assert excinfo.value.status_code == 502
    assert "crash at db:5432" not in excinfo.value.detail
    assert "Falha ao provisionar conexão no provedor WhatsApp." == excinfo.value.detail


@pytest.mark.asyncio
async def test_evolution_provider_set_webhook():
    provider = EvolutionProvider(mock_mode=True)
    res = await provider.set_webhook("inst_1", "http://webhook.url/test")
    assert res["status"] == "SUCCESS"
    assert res["webhook"]["url"] == "http://webhook.url/test"
