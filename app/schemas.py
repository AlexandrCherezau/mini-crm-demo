"""Request validation models."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .db import MANAGERS

Status = Literal["new", "in_progress", "paid", "lost"]
Source = Literal["site", "telegram", "avito"]

MAX_AMOUNT = 100_000_000


def _strip(value: str) -> str:
    return value.strip()


class LeadCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=160)
    request: str = Field(default="", max_length=2000)
    source: Source = "site"
    amount: int = Field(default=0, ge=0, le=MAX_AMOUNT)
    manager: Optional[str] = None

    _clean = field_validator("name", "phone", "email", "request")(_strip)

    @field_validator("manager")
    @classmethod
    def known_manager(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in MANAGERS:
            raise ValueError("неизвестный менеджер")
        return value


class WebhookLead(BaseModel):
    """Payload a website form (or Tilda/WordPress hook) would send."""

    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=160)
    message: str = Field(default="", max_length=2000)
    source: Source = "site"
    budget: int = Field(default=0, ge=0, le=MAX_AMOUNT)

    _clean = field_validator("name", "phone", "email", "message")(_strip)


class StatusChange(BaseModel):
    status: Status
    author: str = Field(default="Менеджер", min_length=1, max_length=80)


class LeadPatch(BaseModel):
    amount: Optional[int] = Field(default=None, ge=0, le=MAX_AMOUNT)
    manager: Optional[str] = None
    author: str = Field(default="Менеджер", min_length=1, max_length=80)

    @field_validator("manager")
    @classmethod
    def known_manager(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in MANAGERS:
            raise ValueError("неизвестный менеджер")
        return value


class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    author: str = Field(default="Менеджер", min_length=1, max_length=80)

    _clean = field_validator("text")(_strip)
