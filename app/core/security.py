import hashlib
import hmac
import time
from typing import Any, Dict, Optional

import jwt

from app.core.config import settings


def create_access_token(
    clinic_id: str,
    user_id: str = "user",
    expires_in: int = 3600,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Emite um JWT compatível com a validação do backend.
    Em produção, o token é emitido pelo sistema de autenticação do Lunae Care
    (mesmo segredo/issuer/audience); esta função serve a testes e ferramentas de dev.
    """
    now = int(time.time())
    payload: Dict[str, Any] = {
        "sub": user_id,
        settings.JWT_CLINIC_CLAIM: clinic_id,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": now + expires_in,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Valida assinatura, expiração, issuer e audience. Lança jwt.PyJWTError."""
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
        options={"require": ["exp", "sub", "iss", "aud"]},
    )


def derive_webhook_key(instance_id: str) -> str:
    """
    Chave de webhook única por instância (HMAC do ID da instância com o segredo global).
    Rotacionável alterando WEBHOOK_SECRET; vazamento de uma URL não afeta outras instâncias.
    """
    return hmac.new(
        settings.WEBHOOK_SECRET.encode(),
        instance_id.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_webhook_key(instance_id: str, provided_key: str) -> bool:
    return hmac.compare_digest(derive_webhook_key(instance_id), provided_key or "")
