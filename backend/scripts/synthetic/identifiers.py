"""Small helpers for generating stable, plausible-looking identifiers.

Kept separate from the behavioral logic so the "what does an ID/device
fingerprint/IP look like" concerns don't clutter the generation logic
that actually implements the abuse scenarios.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

import numpy as np


def new_id(rng: np.random.Generator) -> str:
    """A UUID4-shaped identifier derived from the seeded RNG.

    Using the seeded generator (rather than `uuid.uuid4()`, which is
    not seedable) means two runs with the same `random_seed` produce
    byte-identical output, IDs included -- required for the dataset to
    be truly reproducible.
    """
    raw = bytearray(rng.bytes(16))
    raw[6] = (raw[6] & 0x0F) | 0x40  # version 4
    raw[8] = (raw[8] & 0x3F) | 0x80  # variant bits
    return str(uuid.UUID(bytes=bytes(raw)))


def device_fingerprint(rng: np.random.Generator) -> str:
    """A stable-looking opaque device fingerprint (as if hashed client-side)."""
    raw = rng.bytes(16)
    return hashlib.sha256(raw).hexdigest()[:32]


def private_ip(rng: np.random.Generator) -> str:
    """A syntactically valid IPv4 address in a private range.

    We deliberately stay in private ranges since these are simulated
    merchant-side network identifiers, not real public IPs.
    """
    block = rng.choice([10, 172, 192])
    if block == 10:
        return f"10.{rng.integers(0, 256)}.{rng.integers(0, 256)}.{rng.integers(1, 255)}"
    if block == 172:
        return f"172.{rng.integers(16, 32)}.{rng.integers(0, 256)}.{rng.integers(1, 255)}"
    return f"192.168.{rng.integers(0, 256)}.{rng.integers(1, 255)}"


@dataclass
class IdentifierPools:
    """Pre-allocated pools of device/IP identifiers to draw from.

    Using pools (rather than minting a fresh device/IP per link) is
    what makes "sharing" possible: several customers can be assigned
    the same pool entry.
    """

    devices: list[str]
    ips: list[str]
