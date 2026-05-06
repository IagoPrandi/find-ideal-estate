from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuthRegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str | None = None


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthGoogleLoginRequest(BaseModel):
    credential: str


class AuthUserRead(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    is_active: bool
    created_at: datetime
    role: str = "user"


class AuthStatusRead(BaseModel):
    is_authenticated: bool
    user: AuthUserRead | None = None
    session_expires_at: datetime | None = None
