"""Configuration for the synthetic data generator.

Every knob that controls dataset size or behavioral intensity lives
here so the whole thing can be scaled up/down (e.g. for a bigger demo
dataset, or a tiny one for fast tests) from one place, without digging
through generation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Fixed reference "now" for the synthetic dataset. Using a wall-clock
# `datetime.now()` default would silently break seed-based
# reproducibility (same seed, different day -> different output), so
# the default anchor is a fixed constant. Pass an explicit
# `window_end` (or `--window-end` on the CLI) to generate a dataset
# anchored to a different date.
DEFAULT_WINDOW_END = datetime(2026, 6, 1, tzinfo=timezone.utc)


@dataclass
class GeneratorConfig:
    # Reproducibility
    random_seed: int = 42

    # Overall time window the synthetic history spans.
    window_end: datetime = field(default_factory=lambda: DEFAULT_WINDOW_END)
    window_days: int = 90

    # Volume knobs -- these are customer *counts*, not row counts.
    merchant_count: int = 5
    normal_customer_count: int = 600
    shared_infra_customer_count: int = 250
    abuse_customer_count: int = 150

    # Legitimate shared-infrastructure clusters (families/offices).
    shared_infra_cluster_size_min: int = 2
    shared_infra_cluster_size_max: int = 5
    # Fraction of shared-infra clusters that share a device (rest share
    # only an IP, or both) -- kept mixed so "shared device" alone is
    # never a perfect abuse/non-abuse discriminator.
    shared_infra_share_device_prob: float = 0.5
    shared_infra_share_ip_prob: float = 0.7

    # Coordinated abuse rings.
    abuse_ring_size_min: int = 3
    abuse_ring_size_max: int = 8
    # Each ring independently rolls whether it exhibits each signal, so
    # rings display different *combinations* of signals rather than a
    # single tell-tale pattern.
    abuse_share_device_prob: float = 0.55
    abuse_share_ip_prob: float = 0.6
    abuse_creation_burst_prob: float = 0.7
    abuse_high_velocity_prob: float = 0.65
    abuse_similar_amount_prob: float = 0.6
    abuse_concentrated_window_prob: float = 0.6
    abuse_high_return_prob: float = 0.45

    # Noise -- keeps the classes from being trivially separable.
    # Some normal/shared-infra customers get one mildly "suspicious"
    # trait (e.g. a short burst of activity from a genuine sale event),
    # and some abuse ring members get diluted/normal-looking behavior.
    benign_noise_prob: float = 0.08
    abuse_dilution_prob: float = 0.15

    currency: str = "INR"

    def window_start(self) -> datetime:
        return self.window_end - timedelta(days=self.window_days)
