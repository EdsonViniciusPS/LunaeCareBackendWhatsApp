import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.security import derive_webhook_key
from app.models.connection import WhatsAppConnection
from app.providers.evolution import EvolutionProvider
from tests.helpers import auth

URL = "/api/v1/whatsapp/connections"
WEBHOOK = "/api/v1/whatsapp/webhooks/evolution"


def test_encrypt_roundtrip_and_not_plaintext():
    token = encrypt_secret("segredo-da-instancia")
    assert token != "segredo-da-instancia"
    assert "segredo" not in token
    assert decrypt_secret(token) == "segredo-da-instancia"
    assert decrypt_secret("lixo") is None


@pytest.mark.asyncio
async def test_instance_token_encrypted_at_rest(client: AsyncClient, db_session):
    resp = await client.post(URL, headers=auth("clinica_a"))
    assert resp.status_code == 201
    # O token da instância nunca é exposto pela API
    assert "token" not in str(resp.json()).lower()
    assert "mock_key_" not in str(resp.json())

    row = (await db_session.execute(select(WhatsAppConnection))).scalar_one()
    assert row.provider_token_encrypted
    assert "mock_key_" not in row.provider_token_encrypted
    assert decrypt_secret(row.provider_token_encrypted).startswith("mock_key_")


@pytest.mark.asyncio
async def test_qr_code_not_persisted(client: AsyncClient, db_session):
    h = auth("clinica_a")
    conn_id = (await client.post(URL, headers=h)).json()["id"]
    r = await client.post(f"{URL}/{conn_id}/connect", headers=h)
    assert r.json()["qrcode"]
    row = (await db_session.execute(select(WhatsAppConnection))).scalar_one()
    assert not hasattr(row, "qr_code")


async def _create(client, clinic="clinica_a"):
    r = await client.post(URL, headers=auth(clinic))
    return r.json()


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_key(client: AsyncClient):
    conn = await _create(client)
    payload = {"event": "connection.update", "instance": conn["provider_instance_id"],
               "data": {"state": "open"}}
    resp = await client.post(f"{WEBHOOK}/chave-errada", json=payload)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_key_of_other_instance_rejected(client: AsyncClient):
    a = await _create(client, "clinica_a")
    b = await _create(client, "clinica_b")
    key_b = derive_webhook_key(b["provider_instance_id"])
    payload = {"event": "connection.update", "instance": a["provider_instance_id"],
               "data": {"state": "open"}}
    assert (await client.post(f"{WEBHOOK}/{key_b}", json=payload)).status_code == 403
    got = await client.get(f"{URL}/{a['id']}", headers=auth("clinica_a"))
    assert got.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_webhook_unknown_instance_same_response(client: AsyncClient):
    key = derive_webhook_key("lunae_inexistente")
    payload = {"event": "connection.update", "instance": "lunae_inexistente", "data": {"state": "open"}}
    assert (await client.post(f"{WEBHOOK}/{key}", json=payload)).status_code == 403


@pytest.mark.asyncio
async def test_webhook_updates_connection_state(client: AsyncClient, mock_provider: EvolutionProvider):
    conn = await _create(client)
    inst = conn["provider_instance_id"]
    key = derive_webhook_key(inst)

    open_evt = {"event": "connection.update", "instance": inst, "data": {"state": "open"}}
    mock_provider._mock_instances[inst]["state"] = "open"  # provedor reflete o evento
    resp = await client.post(f"{WEBHOOK}/{key}", json=open_evt)
    assert resp.status_code == 200
    got = await client.get(f"{URL}/{conn['id']}", headers=auth("clinica_a"))
    assert got.json()["status"] == "connected"
    assert got.json()["connected_at"] is not None

    close_evt = {"event": "CONNECTION_UPDATE", "instance": inst, "data": {"state": "close"}}
    mock_provider._mock_instances[inst]["state"] = "close"
    assert (await client.post(f"{WEBHOOK}/{key}", json=close_evt)).status_code == 200
    got = await client.get(f"{URL}/{conn['id']}", headers=auth("clinica_a"))
    assert got.json()["status"] == "disconnected"


@pytest.mark.asyncio
async def test_webhook_duplicate_is_idempotent(client: AsyncClient, mock_provider: EvolutionProvider):
    conn = await _create(client)
    inst = conn["provider_instance_id"]
    key = derive_webhook_key(inst)
    mock_provider._mock_instances[inst]["state"] = "open"
    evt = {"event": "connection.update", "instance": inst, "data": {"state": "open"}}
    for _ in range(3):
        assert (await client.post(f"{WEBHOOK}/{key}", json=evt)).status_code == 200
    got = await client.get(f"{URL}/{conn['id']}", headers=auth("clinica_a"))
    assert got.json()["status"] == "connected"


@pytest.mark.asyncio
async def test_webhook_invalid_payload(client: AsyncClient):
    resp = await client.post(f"{WEBHOOK}/x", content=b"nao-json",
                             headers={"Content-Type": "application/json"})
    assert resp.status_code == 400
