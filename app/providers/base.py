from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class WhatsAppProvider(ABC):
    """
    Interface abstrata que desacopla os serviços internos do Lunae Care
    de provedores específicos (Evolution API, Meta Cloud API, etc).
    """

    @abstractmethod
    async def create_instance(
        self,
        instance_name: str,
        webhook_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cria uma nova instância no provedor."""
        pass

    @abstractmethod
    async def connect(
        self,
        instance_name: str
    ) -> Dict[str, Any]:
        """Inicia o processo de conexão e gera QR Code ou código de pareamento."""
        pass

    @abstractmethod
    async def get_connection_state(
        self,
        instance_name: str
    ) -> Dict[str, Any]:
        """Verifica o estado atual da conexão no provedor."""
        pass

    @abstractmethod
    async def disconnect(
        self,
        instance_name: str
    ) -> Dict[str, Any]:
        """Desconecta a sessão do WhatsApp no provedor."""
        pass

    @abstractmethod
    async def delete_instance(
        self,
        instance_name: str
    ) -> Dict[str, Any]:
        """Exclui a instância e limpa os dados da sessão no provedor."""
        pass

    @abstractmethod
    async def send_text_message(
        self,
        instance_name: str,
        recipient: str,
        text: str
    ) -> Dict[str, Any]:
        """Envia uma mensagem de texto simples."""
        pass
