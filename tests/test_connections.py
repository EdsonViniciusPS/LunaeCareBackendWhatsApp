import pytest
from httpx import AsyncClient

from app.providers.evolution import EvolutionProvider
from tests.helpers import auth

URL = "/api/v1/whatsapp/connections"


@pytest.mark.asyncio
async def test_connection_lifecycle(client: AsyncClient):
    h = auth("clinic_test_01")

    create_resp = await client.post(URL, headers=h, json={"phone_number": "5511999999999"})
    assert create_resp.status_code == 201
    conn_data = create_resp.json()
    conn_id = conn_data["id"]
    assert conn_data["clinic_id"] == "clinic_test_01"
    assert conn_data["status"] == "pending"
    assert conn_data["provider"] == "evolution"
    assert conn_data["provider_instance_id"].startswith("lunae_")

    get_resp = await client.get(f"{URL}/{conn_id}", headers=h)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == conn_id

    connect_resp = await client.post(f"{URL}/{conn_id}/connect", headers=h)
    assert connect_resp.status_code == 200
    connect_data = connect_resp.json()
    assert connect_data["status"] == "connecting"
    assert connect_data["qrcode"] is not None

    items = (await client.get(URL, headers=h)).json()
    assert len(items) == 1
    assert items[0]["id"] == conn_id

    disconnect_resp = await client.post(f"{URL}/{conn_id}/disconnect", headers=h)
    assert disconnect_resp.status_code == 200
    assert disconnect_resp.json()["status"] == "disconnected"

    delete_resp = await client.delete(f"{URL}/{conn_id}", headers=h)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["status"] == "deleted"

    assert (await client.get(f"{URL}/{conn_id}", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_connection_not_found_operations(client: AsyncClient):
    h = auth("clinic_test_02")
    missing = "00000000-0000-0000-0000-000000000000"

    assert (await client.get(f"{URL}/{missing}", headers=h)).status_code == 404
    assert (await client.post(f"{URL}/{missing}/connect", headers=h)).status_code == 404
    assert (await client.post(f"{URL}/{missing}/disconnect", headers=h)).status_code == 404
    assert (await client.delete(f"{URL}/{missing}", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_connection_state_sync(client: AsyncClient, mock_provider: EvolutionProvider):
    h = auth("clinic_test_03")

    create_resp = await client.post(URL, headers=h)
    assert create_resp.status_code == 201
    conn_id = create_resp.json()["id"]
    instance_id = create_resp.json()["provider_instance_id"]

    mock_provider._mock_instances[instance_id]["state"] = "open"

    data = (await client.get(f"{URL}/{conn_id}", headers=h)).json()
    assert data["status"] == "connected"
    assert data["connected_at"] is not None
