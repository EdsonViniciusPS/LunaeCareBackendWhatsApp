from app.providers.base import WhatsAppProvider
from app.providers.evolution import EvolutionProvider
from app.core.config import settings

_provider_instance: WhatsAppProvider | None = None


def get_whatsapp_provider() -> WhatsAppProvider:
    global _provider_instance
    if _provider_instance is None:
        if settings.WHATSAPP_PROVIDER == "evolution":
            _provider_instance = EvolutionProvider()
        else:
            _provider_instance = EvolutionProvider()
    return _provider_instance


__all__ = ["WhatsAppProvider", "EvolutionProvider", "get_whatsapp_provider"]
