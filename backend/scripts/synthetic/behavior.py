"""Behavioral sampling helpers.

These functions turn a small set of parameters (how many transactions,
whether activity is concentrated in time, whether amounts are similar
across a group, ...) into concrete timestamps and amounts. Kept
separate from `builder.py` so the "what does normal vs. abusive
activity look like numerically" logic can be read and reasoned about
on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np


def sample_timestamps(
    rng: np.random.Generator,
    count: int,
    window_start: datetime,
    window_end: datetime,
    concentrated: bool,
    concentration_days: float = 2.0,
) -> list[datetime]:
    """Sample `count` timestamps within [window_start, window_end].

    If `concentrated`, all timestamps fall within a random sub-window
    of length `concentration_days`, simulating a burst of activity.
    Otherwise timestamps are spread uniformly across the full window.
    """
    total_seconds = (window_end - window_start).total_seconds()
    if total_seconds <= 0:
        return [window_start for _ in range(count)]

    if concentrated:
        max_start_offset = max(total_seconds - concentration_days * 86400, 0)
        sub_start_offset = rng.uniform(0, max_start_offset) if max_start_offset > 0 else 0
        sub_window_start = window_start + timedelta(seconds=sub_start_offset)
        span_seconds = min(concentration_days * 86400, total_seconds)
        offsets = rng.uniform(0, span_seconds, size=count)
        return sorted(sub_window_start + timedelta(seconds=float(o)) for o in offsets)

    offsets = rng.uniform(0, total_seconds, size=count)
    return sorted(window_start + timedelta(seconds=float(o)) for o in offsets)


def sample_amounts(
    rng: np.random.Generator,
    count: int,
    base_amount: float,
    relative_spread: float,
) -> list[float]:
    """Sample `count` positive amounts clustered around `base_amount`.

    `relative_spread` is the coefficient of variation: 0.03-0.08 gives
    tightly similar amounts (used for coordinated abuse rings), while
    0.4-0.8 gives the kind of varied amounts normal customers show.
    """
    std = max(base_amount * relative_spread, 1.0)
    values = rng.normal(loc=base_amount, scale=std, size=count)
    values = np.clip(values, 10.0, None)
    return [round(float(v), 2) for v in values]


@dataclass
class TransactionProfile:
    """Parameters controlling one customer's simulated transaction history."""

    num_transactions: int
    base_amount: float
    relative_spread: float
    concentrated: bool
    concentration_days: float
    return_probability: float
    account_created_at: datetime
