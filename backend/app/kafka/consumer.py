"""
TrustGraph Kafka consumer.

This module is intentionally isolated from the core intelligence pipeline.

The consumer:
    Kafka
      ↓
    JSON
      ↓
    TrustGraphEvent validation
      ↓
    application callback

It does NOT:
- calculate risk
- invoke ML
- invoke Gemini
- execute policy
- modify PostgreSQL
- modify M2/M3
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer

from app.kafka.events import TrustGraphEvent


DEFAULT_TOPIC = "trustgraph.events"
DEFAULT_GROUP = "trustgraph-consumer"


EventHandler = Callable[
    [TrustGraphEvent],
    Awaitable[None],
]


class KafkaEventConsumer:
    """
    Asynchronous TrustGraph Kafka consumer.

    Kafka connection defaults:
        Docker: kafka:9092
        Host:   localhost:9094

    Inside the TrustGraph Docker network, kafka:9092 should be used.
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str | None = None,
        topic: str | None = None,
        group_id: str | None = None,
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

        self.group_id = (
            group_id
            or os.getenv(
                "KAFKA_CONSUMER_GROUP",
                DEFAULT_GROUP,
            )
        )

        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        """Start the Kafka consumer."""

        if self._consumer is not None:
            return

        self._consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )

        await self._consumer.start()

    async def consume_one(
        self,
        handler: EventHandler,
        *,
        timeout_ms: int = 10000,
    ) -> TrustGraphEvent | None:
        """
        Consume one event.

        The offset is committed only after:
            1. JSON parsing succeeds
            2. Pydantic validation succeeds
            3. The application handler succeeds

        This gives us a safe acknowledgment boundary.
        """

        if self._consumer is None:
            raise RuntimeError(
                "KafkaEventConsumer is not started. "
                "Call await consumer.start() first."
            )

        try:
            message = await self._consumer.getone()

        except TimeoutError:
            return None

        # ---------------------------------------------------------------
        # Deserialize JSON.
        # ---------------------------------------------------------------

        try:
            payload = json.loads(
                message.value.decode("utf-8")
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            print(
                "KAFKA EVENT REJECTED — invalid JSON:",
                exc,
            )
            return None

        # ---------------------------------------------------------------
        # Validate TrustGraph event contract.
        # ---------------------------------------------------------------

        try:
            event = TrustGraphEvent.model_validate(
                payload
            )

        except Exception as exc:
            print(
                "KAFKA EVENT REJECTED — schema validation failed:",
                exc,
            )
            return None

        # ---------------------------------------------------------------
        # Application processing.
        # ---------------------------------------------------------------

        await handler(event)

        # ---------------------------------------------------------------
        # Acknowledge only after successful processing.
        # ---------------------------------------------------------------

        await self._consumer.commit()

        return event

    async def stop(self) -> None:
        """Stop the consumer safely."""

        if self._consumer is None:
            return

        await self._consumer.stop()
        self._consumer = None

    async def __aenter__(self) -> "KafkaEventConsumer":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        await self.stop()