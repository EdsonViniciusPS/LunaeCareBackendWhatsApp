from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    clinic_id: str
    phone_number: str
    display_name: Optional[str] = None
    patient_id: Optional[str] = None
    created_at: datetime


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    clinic_id: str
    connection_id: str
    contact_id: str
    status: str
    assigned_user_id: Optional[str] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    contact: Optional[ContactResponse] = None
