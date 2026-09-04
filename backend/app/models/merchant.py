"""Merchant entity.

A merchant is the tenant whose payment activity we are protecting.
Everything else (customers, transactions, ...) hangs off a merchant.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Merchant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "merchants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    customers: Mapped[list["Customer"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"Merchant(id={self.id!r}, name={self.name!r})"
