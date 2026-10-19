from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ConnectionCreate(BaseModel):
    phone_number: Optional[str] = None


class ConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    clinic_id: str
    provider: str
    provider_instance_id: str
    phone_number: Optional[str] = None
    status: str
    connected_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ConnectionConnectResponse(BaseModel):
    connection_id: str
    status: str
    qrcode: Optional[str] = None
    pairing_code: Optional[str] = None
    message: str


class ConnectionDisconnectResponse(BaseModel):
    connection_id: str
    status: str
    message: str


class ConnectionDeleteResponse(BaseModel):
    connection_id: str
    status: str
    message: str
