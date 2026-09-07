from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Enter a valid email address")
        return normalized


class LoginRequest(RegisterRequest):
    pass


class EmailVerificationRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return RegisterRequest.normalize_email(value)


class EmailVerificationConfirmRequest(EmailVerificationRequest):
    code: str = Field(pattern=r"^\d{6}$")


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return RegisterRequest.normalize_email(value)


class PasswordResetConfirmRequest(PasswordResetRequest):
    code: str = Field(pattern=r"^\d{6}$")
    password: str = Field(min_length=8, max_length=256)


class MessageRead(BaseModel):
    message: str


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=8, max_length=256)
    confirmation: Literal["DELETE"]


class UserRead(BaseModel):
    id: str
    email: str
    is_admin: bool
    email_verified: bool
    created_at: datetime


class AuthRead(BaseModel):
    user: UserRead
    expires_at: datetime


class SessionRead(BaseModel):
    id: str
    created_at: datetime
    expires_at: datetime
    current: bool
