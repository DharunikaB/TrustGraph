"""
TrustGraph Kafka event contract.

This module defines the stable event shape exchanged through Kafka.

The event contract intentionally contains only the information needed
to represent an authentication/payment event at the ingestion boundary.

It does not contain:
- ground truth
- risk scores
- ML predictions
- Gemini output
- policy decisions

Those belong to downstream TrustGraph intelligence layers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TrustGraphEvent(BaseModel):
    """
    Event published to the TrustGraph Kafka topic.

    Kafka transports observable activity.
    TrustGraph intelligence determines what that activity means.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    event_id: str = Field(
        min_length=1,
        description="Unique identifier for the event.",
    )

    event_type: Literal[
        "payment",
        "authentication",
    ]

    merchant_id: str = Field(
        min_length=1,
    )

    customer_id: str = Field(
        min_length=1,
    )

    device_id: str | None = None

    network_id: str | None = None

    amount: float | None = Field(
        default=None,
        ge=0,
    )

    currency: str | None = None

    timestamp: datetime


def event_to_json(event: TrustGraphEvent) -> str:
    """
    Serialize a TrustGraph event into the JSON representation
    sent to Kafka.
    """

    return event.model_dump_json()