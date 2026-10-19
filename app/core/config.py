from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

_INSECURE_DEFAULTS = {
    "lunae_internal_secret_change_me",
    "lunae_webhook_secret_change_me",
    "lunae_jwt_secret_change_me_please_32b",
    "lunae_encryption_key_change_me",
    "evolution_global_api_key_change_me",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    APP_NAME: str = "Lunae Care WhatsApp Backend"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Segurança e Autenticação
    INTERNAL_API_KEY: str = "lunae_internal_secret_change_me"
    WEBHOOK_SECRET: str = "lunae_webhook_secret_change_me"

    # JWT emitido pelo Lunae Care (a identidade da clínica vem SEMPRE do token)
    JWT_SECRET: str = "lunae_jwt_secret_change_me_please_32b"
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "lunaecare"
    JWT_AUDIENCE: str = "lunaecare-whatsapp"
    JWT_CLINIC_CLAIM: str = "clinic_id"

    # Criptografia de credenciais em repouso (chave fora do banco)
    ENCRYPTION_KEY: str = "lunae_encryption_key_change_me"

    # Banco de Dados
    DATABASE_URL: str = "postgresql+asyncpg://lunae_user:lunae_password@whatsapp-db:5432/lunaecare_whatsapp"
    DATABASE_SYNC_URL: Optional[str] = None

    # Redis
    REDIS_URL: str = "redis://whatsapp-redis:6379/0"

    # Provedor WhatsApp
    WHATSAPP_PROVIDER: str = "evolution"
    EVOLUTION_API_URL: str = "http://evolution-api:8080"
    EVOLUTION_API_KEY: str = "evolution_global_api_key_change_me"
    EVOLUTION_WEBHOOK_URL: str = "http://lunaecare-whatsapp:8000/api/v1/whatsapp/webhooks/evolution"
    EVOLUTION_MOCK_MODE: bool = False

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_production(self):
        if self.ENVIRONMENT.lower() == "production":
            bad = [
                name for name in (
                    "INTERNAL_API_KEY", "WEBHOOK_SECRET", "JWT_SECRET",
                    "ENCRYPTION_KEY", "EVOLUTION_API_KEY",
                )
                if getattr(self, name) in _INSECURE_DEFAULTS
            ]
            if bad:
                raise ValueError(
                    f"Segredos padrão inseguros em produção: {', '.join(bad)}"
                )
        return self


settings = Settings()
