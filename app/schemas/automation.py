from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class AutomationRuleCreate(BaseModel):
    connection_id: str = Field(..., description="ID da conexão ativa para envio das mensagens")
    event_trigger: str = Field(
        ...,
        description="Gatilho do evento (ex: 'appointment_created', 'appointment_reminder_24h', 'appointment_cancelled')"
    )
    template: str = Field(
        ...,
        min_length=5,
        max_length=4096,
        description="Template da mensagem com placeholders {{patient_name}}, {{professional_name}}, {{appointment_date}}, {{appointment_time}}"
    )
    enabled: int = Field(default=1, ge=0, le=1, description="1 para ativo, 0 para inativo")
    settings: Optional[Dict[str, Any]] = Field(default=None, description="Configurações extras (ex: {'hours_before': 24})")


class AutomationRuleUpdate(BaseModel):
    connection_id: Optional[str] = None
    event_trigger: Optional[str] = None
    template: Optional[str] = None
    enabled: Optional[int] = Field(default=None, ge=0, le=1)
    settings: Optional[Dict[str, Any]] = None


class AutomationRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    clinic_id: str
    connection_id: str
    event_trigger: str
    template: str
    enabled: int
    settings: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class AutomationRuleToggleAllRequest(BaseModel):
    enabled: bool = Field(..., description="True para ativar todas as automações da clínica, False para pausar todas")


class AgendaEventPayload(BaseModel):
    event: str = Field(
        ...,
        description="Tipo de evento da agenda: 'appointment.created', 'appointment.rescheduled', 'appointment.cancelled'"
    )
    appointment_id: str = Field(..., description="ID da consulta na agenda do Lunae Care")
    patient_id: Optional[str] = Field(default=None, description="ID do paciente no Lunae Care")
    patient_name: str = Field(..., min_length=1, description="Nome do paciente")
    phone_number: str = Field(..., min_length=8, max_length=32, description="Número de WhatsApp do paciente")
    professional_name: str = Field(..., min_length=1, description="Nome do profissional de saúde")
    appointment_datetime: datetime = Field(..., description="Data e hora da consulta (ISO 8601 com timezone)")
    clinic_id: Optional[str] = Field(default=None, description="ID da clínica (obrigatório se chamado com token interno global)")


class ContactPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    clinic_id: str
    contact_id: str
    purpose: str
    consent_status: str
    consent_source: Optional[str] = None
    consented_at: Optional[datetime] = None
    opted_out_at: Optional[datetime] = None
    updated_at: datetime


class ContactPreferenceUpdateRequest(BaseModel):
    consent_status: str = Field(..., pattern="^(opted_in|opted_out)$", description="'opted_in' ou 'opted_out'")
    purpose: str = Field(default="appointment_reminders", description="Finalidade da preferência de contato")
