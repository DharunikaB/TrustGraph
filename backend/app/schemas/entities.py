"""Pydantic schemas for validating data in/out of the API and loaders.

These mirror the ORM models but are kept as separate, independent
definitions (standard FastAPI/Pydantic practice) so that API
contracts don't accidentally change just because a DB column changes,
and so the synthetic data generator has a validation layer independent
of SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class TransactionStatusSchema(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


class MerchantBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MerchantCreate(MerchantBase):
    id: str


class MerchantRead(MerchantBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class CustomerBase(BaseModel):
    merchant_id: str
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)


class CustomerCreate(CustomerBase):
    id: str


class CustomerRead(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class DeviceBase(BaseModel):
    device_fingerprint: str = Field(min_length=8, max_length=128)


class DeviceCreate(DeviceBase):
    id: str


class DeviceRead(DeviceBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class NetworkIdentifierBase(BaseModel):
    ip_address: str = Field(min_length=3, max_length=64)


class NetworkIdentifierCreate(NetworkIdentifierBase):
    id: str


class NetworkIdentifierRead(NetworkIdentifierBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class CustomerDeviceLinkCreate(BaseModel):
    id: str
    customer_id: str
    device_id: str
    first_seen: datetime
    last_seen: datetime

    @field_validator("last_seen")
    @classmethod
    def last_seen_not_before_first_seen(cls, v: datetime, info) -> datetime:
        first_seen = info.data.get("first_seen")
        if first_seen is not None and v < first_seen:
            raise ValueError("last_seen cannot be before first_seen")
        return v


class CustomerNetworkLinkCreate(BaseModel):
    id: str
    customer_id: str
    network_id: str
    first_seen: datetime
    last_seen: datetime

    @field_validator("last_seen")
    @classmethod
    def last_seen_not_before_first_seen(cls, v: datetime, info) -> datetime:
        first_seen = info.data.get("first_seen")
        if first_seen is not None and v < first_seen:
            raise ValueError("last_seen cannot be before first_seen")
        return v


class TransactionCreate(BaseModel):
    id: str
    customer_id: str
    device_id: str | None = None
    network_id: str | None = None
    amount: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3, default="INR")
    status: TransactionStatusSchema = TransactionStatusSchema.SUCCESS
    created_at: datetime


class TransactionRead(TransactionCreate):
    model_config = ConfigDict(from_attributes=True)


class OrderCreate(BaseModel):
    id: str
    transaction_id: str
    order_amount: float = Field(gt=0)
    created_at: datetime


class OrderRead(OrderCreate):
    model_config = ConfigDict(from_attributes=True)


class ReturnCreate(BaseModel):
    id: str
    order_id: str
    amount: float = Field(gt=0)
    reason: str = Field(min_length=1, max_length=200, default="unspecified")
    created_at: datetime


class ReturnRead(ReturnCreate):
    model_config = ConfigDict(from_attributes=True)


class GroundTruthLabel(str, Enum):
    """Which synthetic behavioral category a customer was generated under.

    This is deliberately kept OUT of the feature tables the future
    detector will consume -- it lives only in the ground-truth dataset
    used for evaluation.
    """

    NORMAL = "normal"
    LEGITIMATE_SHARED_INFRA = "legitimate_shared_infra"
    COORDINATED_ABUSE = "coordinated_abuse"


class GroundTruthCreate(BaseModel):
    customer_id: str
    label: GroundTruthLabel
    cluster_id: str | None = Field(
        default=None,
        description="Groups customers generated together as one coordinated "
        "scenario (shared device ring, shared IP household, abuse ring). "
        "Null for standalone normal customers.",
    )
    is_abuse: bool


class GroundTruthRead(GroundTruthCreate):
    model_config = ConfigDict(from_attributes=True)
