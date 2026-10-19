import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    # Deriva uma chave Fernet de 32 bytes a partir do segredo configurado.
    digest = hashlib.sha256(settings.ENCRYPTION_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(token: Optional[str]) -> Optional[str]:
    if token is None:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
