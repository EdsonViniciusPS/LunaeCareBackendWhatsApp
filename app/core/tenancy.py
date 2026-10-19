import re
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.security import decode_access_token


@dataclass(frozen=True)
class TenantContext:
    clinic_id: str
    user_id: str | None = None


CLINIC_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_tenant_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> TenantContext:
    """
    Resolve a clínica a partir da identidade autenticada (JWT Bearer).
    Qualquer clinic_id enviado em headers/body/query é ignorado.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Autenticação necessária.")

    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expirado.")
    except jwt.PyJWTError:
        raise _unauthorized("Token inválido.")

    clinic_id = claims.get(settings.JWT_CLINIC_CLAIM)
    if not isinstance(clinic_id, str) or not CLINIC_ID_REGEX.match(clinic_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token sem clínica autorizada válida."
        )

    return TenantContext(clinic_id=clinic_id, user_id=str(claims["sub"]))
