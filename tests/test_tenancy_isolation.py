import time

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.helpers import auth

URL = "/api/v1/whatsapp/connections"


@pytest.mark.asyncio
async def test_missing_token_is_rejected(client: AsyncClient):
    resp = await client.get(URL)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_x_clinic_id_header_alone_is_not_authentication(client: AsyncClient):
    resp = await client.get(URL, headers={"X-Clinic-ID": "clinica_a"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_spoofed_clinic_header_is_ignored(client: AsyncClient):
    # Token da clínica B + header tentando se passar pela clínica A
    created = await client.post(URL, headers=auth("clinica_a"))
    conn_id = created.json()["id"]

    headers = {**auth("clinica_b"), "X-Clinic-ID": "clinica_a"}
    resp = await client.get(f"{URL}/{conn_id}", headers=headers)
    assert resp.status_code == 404
    assert (await client.get(URL, headers=headers)).json() == []


@pytest.mark.asyncio
async def test_invalid_signature_rejected(client: AsyncClient):
    forged = jwt.encode(
        {"sub": "x", "clinic_id": "clinica_a", "iss": settings.JWT_ISSUER,
         "aud": settings.JWT_AUDIENCE, "exp": int(time.time()) + 600},
        "outro-segredo-qualquer-com-32-bytes-ok!", algorithm="HS256",
    )
    resp = await client.get(URL, headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_rejected(client: AsyncClient):
    resp = await client.get(URL, headers=auth("clinica_a", expires_in=-10))
    assert resp.status_code == 401
    assert "expirado" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_wrong_audience_rejected(client: AsyncClient):
    headers = auth("clinica_a", extra_claims={"aud": "outro-servico"})
    assert (await client.get(URL, headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_alg_none_rejected(client: AsyncClient):
    token = jwt.encode(
        {"sub": "x", "clinic_id": "clinica_a", "iss": settings.JWT_ISSUER,
         "aud": settings.JWT_AUDIENCE, "exp": int(time.time()) + 600},
        key=None, algorithm="none",
    )
    resp = await client.get(URL, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_without_clinic_claim_forbidden(client: AsyncClient):
    token = jwt.encode(
        {"sub": "x", "iss": settings.JWT_ISSUER, "aud": settings.JWT_AUDIENCE,
         "exp": int(time.time()) + 600},
        settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM,
    )
    resp = await client.get(URL, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invalid_clinic_claim_format_forbidden(client: AsyncClient):
    resp = await client.get(URL, headers=auth("clinica com espacos!@#"))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_multi_tenant_isolation(client: AsyncClient):
    a, b = auth("clinica_medica_sul"), auth("clinica_odonto_norte")

    conn_a_id = (await client.post(URL, headers=a, json={"phone_number": "5511988887777"})).json()["id"]

    assert (await client.get(f"{URL}/{conn_a_id}", headers=b)).status_code == 404
    assert (await client.post(f"{URL}/{conn_a_id}/connect", headers=b)).status_code == 404
    assert (await client.post(f"{URL}/{conn_a_id}/disconnect", headers=b)).status_code == 404
    assert (await client.delete(f"{URL}/{conn_a_id}", headers=b)).status_code == 404
    assert (await client.get(URL, headers=b)).json() == []

    list_a = (await client.get(URL, headers=a)).json()
    assert [c["id"] for c in list_a] == [conn_a_id]


@pytest.mark.asyncio
async def test_three_clinics_isolation(client: AsyncClient):
    clinics = [f"clinica_{i}" for i in range(3)]
    created = [await client.post(URL, headers=auth(c)) for c in clinics]
    ids = {c: r.json()["id"] for c, r in zip(clinics, created)}
    assert all(r.status_code == 201 for r in created)

    for c in clinics:
        items = (await client.get(URL, headers=auth(c))).json()
        assert [i["id"] for i in items] == [ids[c]]
        assert all(i["clinic_id"] == c for i in items)
