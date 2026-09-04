"""
TrustGraph Kafka producer.

This is intentionally an isolated adapter.

The producer does not:
- calculate risk
- invoke ML
- invoke Gemini
- execute policy
- modify the existing intelligence pipeline

Its only responsibility is publishing validated TrustGraph events
to Kafka.
"""

from __future__ import annotations

import os
from typing import Final

from aiokafka import AIOKafkaProducer

from app.kafka.events import TrustGraphEvent, event_to_json


DEFAULT_TOPIC: Final[str] = "trustgraph.events"


class KafkaEventProducer:
    """
    Small asynchronous Kafka producer for TrustGraph events.

    Defaults:
        Host execution: localhost:9094

    Docker execution can override:
        KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str | None = None,
        topic: str | None = None,
    ) -> None:
        self.bootstrap_servers = (
            bootstrap_servers
            or os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS",
                "localhost:9094",
            )
        )

        self.topic = (
            topic
            or os.getenv(
                "KAFKA_TOPIC",
                DEFAULT_TOPIC,
            )
        )

        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        """Start the underlying Kafka producer."""

        if self._producer is not None:
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            acks="all",
        )

        await self._producer.start()

    async def publish(
        self,
        event: TrustGraphEvent,
    ) -> None:
        """
        Publish one validated TrustGraph event.

        The event_id is used as the Kafka message key so events
        can be traced consistently.
        """

        if self._producer is None:
            raise RuntimeError(
                "KafkaEventProducer is not started. "
                "Call await producer.start() first."
            )

        payload = event_to_json(event)

        await self._producer.send_and_wait(
            self.topic,
            key=event.event_id.encode("utf-8"),
            value=payload.encode("utf-8"),
        )

    async def stop(self) -> None:
        """Stop the underlying Kafka producer safely."""

        if self._producer is None:
            return

        await self._producer.stop()
        self._producer = None

    async def __aenter__(self) -> "KafkaEventProducer":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        await self.stop()