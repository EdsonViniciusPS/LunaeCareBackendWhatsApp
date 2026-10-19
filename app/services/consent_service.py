import logging
import re
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import WhatsAppContact, WhatsAppContactPreference
from app.repositories.consent_repository import ConsentRepository
from app.repositories.job_repository import JobRepository

logger = logging.getLogger(__name__)

OPT_OUT_KEYWORDS = {
    "PARAR",
    "SAIR",
    "CANCELAR MENSAGENS",
    "CANCELAR MENSAGEM",
    "NAO QUERO RECEBER",
    "NÃO QUERO RECEBER",
    "STOP",
    "OPTOUT",
    "OPT-OUT",
    "DESCADASTRO",
}

OPT_IN_KEYWORDS = {
    "COMEÇAR",
    "COMECAR",
    "VOLTAR",
    "QUERO RECEBER",
    "START",
}


class ConsentService:
    """
    Serviço de gestão de consentimento e opt-out (LGPD) por paciente e clínica.
    """

    def __init__(
        self,
        consent_repo: Optional[ConsentRepository] = None,
        job_repo: Optional[JobRepository] = None
    ):
        self.consent_repo = consent_repo or ConsentRepository()
        self.job_repo = job_repo or JobRepository()

    def detect_consent_command(self, text: str) -> Optional[str]:
        """
        Retorna 'opt_out', 'opt_in' ou None baseado no texto recebido.
        """
        if not text:
            return None
        cleaned = re.sub(r"[^\w\s-]", "", text.strip().upper())
        if cleaned in OPT_OUT_KEYWORDS:
            return "opt_out"
        if cleaned in OPT_IN_KEYWORDS:
            return "opt_in"
        return None

    async def handle_inbound_message(
        self,
        db: AsyncSession,
        clinic_id: str,
        contact: WhatsAppContact,
        text: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Processa comandos de consentimento enviados pelo paciente via WhatsApp.
        Retorna (foi_comando_de_consentimento, resposta_automatica_se_houver).
        """
        command = self.detect_consent_command(text)
        if command == "opt_out":
            await self.consent_repo.set_preference(
                db,
                clinic_id=clinic_id,
                contact_id=contact.id,
                consent_status="opted_out",
                source="whatsapp_inbound"
            )
            cancelled = await self.job_repo.cancel_jobs_for_phone(db, clinic_id, contact.phone_number)
            logger.info(
                "Paciente %s (%s) solicitou opt-out na clínica %s. %d lembretes pendentes cancelados.",
                contact.id, contact.phone_number, clinic_id, cancelled
            )
            response_msg = (
                "Você não receberá mais lembretes e mensagens automáticas por este canal. "
                "Para reativar a qualquer momento, responda 'COMEÇAR'."
            )
            return True, response_msg

        if command == "opt_in":
            await self.consent_repo.set_preference(
                db,
                clinic_id=clinic_id,
                contact_id=contact.id,
                consent_status="opted_in",
                source="whatsapp_inbound"
            )
            logger.info("Paciente %s (%s) reativou notificações (opt-in) na clínica %s.", contact.id, contact.phone_number, clinic_id)
            response_msg = "Suas notificações e lembretes de consultas foram reativados com sucesso!"
            return True, response_msg

        return False, None

    async def is_opted_out(
        self,
        db: AsyncSession,
        clinic_id: str,
        contact_id: str,
        purpose: str = "appointment_reminders"
    ) -> bool:
        return await self.consent_repo.is_opted_out(db, clinic_id, contact_id, purpose=purpose)

    async def update_preference(
        self,
        db: AsyncSession,
        clinic_id: str,
        contact_id: str,
        consent_status: str,
        source: Optional[str] = None,
        purpose: str = "appointment_reminders"
    ) -> WhatsAppContactPreference:
        return await self.consent_repo.set_preference(
            db,
            clinic_id=clinic_id,
            contact_id=contact_id,
            consent_status=consent_status,
            source=source,
            purpose=purpose
        )
