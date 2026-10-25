from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Permission = Literal["view", "connect", "file_transfer", "terminal", "tunnel", "camera"]
GroupPermission = Literal["view", "connect", "file_transfer", "terminal", "tunnel", "camera", "share"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=1024)
    type: str = "account"


class Registration(StrictModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.@-]{1,80}$")
    display_name: str = Field(default="", max_length=100)
    password: str = Field(min_length=12, max_length=1024)
    password_confirmation: str = Field(min_length=12, max_length=1024)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match")
        return self


class UserCreate(StrictModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_.@-]{1,80}$")
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=1024)
    role: Literal["admin", "member"] = "member"


class UserUpdate(StrictModel):
    enabled: bool


class PasswordChange(StrictModel):
    password: str = Field(min_length=12, max_length=1024)


class GroupCreate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: int | None = Field(default=None, gt=0)
    scope: Literal["internal", "external"] = "internal"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip() or "/" in value or any(ord(c) < 32 for c in value):
            raise ValueError("Group names must be non-empty and cannot contain / or control characters")
        return value.strip()


class DeviceCreate(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,64}$")
    name: str = Field(min_length=1, max_length=120)
    group_id: int = Field(gt=0)
    asset_no: str = Field(default="", max_length=100)
    owner: str = Field(default="", max_length=100)
    location: str = Field(default="", max_length=200)
    platform: str = Field(default="Windows", max_length=100)
    note: str = Field(default="", max_length=1000)


class DeviceUpdate(StrictModel):
    group_id: int = Field(gt=0)
    enabled: bool


class Grant(StrictModel):
    user_id: int = Field(gt=0)
    group_id: int = Field(gt=0)
    permissions: list[GroupPermission] = Field(min_length=1, max_length=7)
    expires_at: int | None = Field(default=None, gt=0)


class DeviceShare(StrictModel):
    device_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,64}$")
    username: str = Field(pattern=r"^[a-zA-Z0-9_.@-]{1,80}$")
    permissions: list[Permission] = Field(min_length=1, max_length=6)
    expires_at: int | None = Field(default=None, gt=0)


class TicketRequest(StrictModel):
    device_id: str = Field(min_length=3, max_length=64)
    controller_id: str = Field(min_length=1, max_length=200)
    action: Literal["connect", "file_transfer", "terminal", "tunnel", "camera"]
    challenge: str = Field(min_length=1, max_length=256)


class TicketVerify(TicketRequest):
    ticket: str = Field(min_length=1, max_length=200)
