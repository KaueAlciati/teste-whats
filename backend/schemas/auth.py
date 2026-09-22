from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    whatsapp_phone: str = Field(min_length=8, max_length=40)
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Nome inválido")
        return normalized


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: SecretStr = Field(min_length=32, max_length=512)
    new_password: SecretStr = Field(min_length=8, max_length=128)
    confirm_new_password: SecretStr = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_must_match(self) -> "ResetPasswordRequest":
        if (
            self.new_password.get_secret_value()
            != self.confirm_new_password.get_secret_value()
        ):
            raise ValueError("A confirmação da nova senha não confere")
        return self


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Nome inválido")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "ProfileUpdateRequest":
        if self.name is None and self.email is None:
            raise ValueError("Informe nome ou e-mail para atualizar")
        return self


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=8, max_length=128)
    confirm_new_password: SecretStr = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_must_match(self) -> "PasswordChangeRequest":
        if (
            self.new_password.get_secret_value()
            != self.confirm_new_password.get_secret_value()
        ):
            raise ValueError("A confirmação da nova senha não confere")
        return self


class DestructiveActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str = Field(min_length=1, max_length=50)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    email: EmailStr | None
    whatsapp_phone: str
    whatsapp_verified: bool
    active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
