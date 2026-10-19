import logging
import pytest
from httpx import AsyncClient

from app.core.logging_filter import SensitiveDataSanitizerFilter
from app.core.rate_limiter import RateLimiter
from tests.helpers import auth


@pytest.mark.asyncio
async def test_security_headers_present_on_all_responses(client: AsyncClient):
    res = await client.get("/")
    assert res.status_code == 200
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert "1; mode=block" in res.headers.get("X-XSS-Protection", "")
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_rate_limiter_blocks_burst(client: AsyncClient):
    headers_fast = auth("clinica_burst")
    conn_res = await client.post("/api/v1/whatsapp/connections", headers=headers_fast, json={})
    conn_id = conn_res.json()["id"]

    # Simula limite de 3 requisições por 60s
    custom_limiter = RateLimiter(times=3, seconds=60, key_prefix="test_burst")

    from fastapi import Request, Response
    req = Request({"type": "http", "headers": [(b"authorization", headers_fast["Authorization"].encode())], "client": ("127.0.0.1", 12345)})
    resp = Response()

    # 3 requisições permitidas
    for _ in range(3):
        await custom_limiter(req, resp)

    # 4ª requisição deve levantar 429
    with pytest.raises(Exception) as excinfo:
        await custom_limiter(req, resp)

    assert excinfo.value.status_code == 429
    assert "Limite de taxa" in excinfo.value.detail


def test_sensitive_data_logging_filter():
    sanitizer = SensitiveDataSanitizerFilter()

    # Teste de máscara de QR Code
    record_qr = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Gerado data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII= para pareamento",
        args=(),
        exc_info=None
    )
    sanitizer.filter(record_qr)
    assert "[QR_CODE_MASKED]" in record_qr.msg
    assert "iVBORw0KGgoAAAANSUhEUg" not in record_qr.msg

    # Teste de máscara de Bearer JWT
    record_jwt = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Tentativa de autenticação com Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.xyz123",
        args=(),
        exc_info=None
    )
    sanitizer.filter(record_jwt)
    assert "Bearer [JWT_MASKED]" in record_jwt.msg
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in record_jwt.msg


@pytest.mark.asyncio
async def test_clinic_metrics_and_isolation(client: AsyncClient):
    headers_a = auth("clinica_metrics_a")
    headers_b = auth("clinica_metrics_b")

    # Cria dados para a clínica A
    conn_a = await client.post("/api/v1/whatsapp/connections", headers=headers_a, json={})
    assert conn_a.status_code == 201

    # Consulta métricas da clínica A
    metrics_a = await client.get("/api/v1/whatsapp/metrics", headers=headers_a)
    assert metrics_a.status_code == 200
    data_a = metrics_a.json()
    assert data_a["clinic_id"] == "clinica_metrics_a"
    assert data_a["connections"]["total"] == 1
    assert data_a["connections"]["by_status"].get("pending") == 1

    # Consulta métricas da clínica B (deve estar limpa)
    metrics_b = await client.get("/api/v1/whatsapp/metrics", headers=headers_b)
    assert metrics_b.status_code == 200
    data_b = metrics_b.json()
    assert data_b["clinic_id"] == "clinica_metrics_b"
    assert data_b["connections"]["total"] == 0


@pytest.mark.asyncio
async def test_system_health_endpoint(client: AsyncClient):
    res = await client.get("/api/v1/whatsapp/metrics/system-health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
