"""Orchestrates synthetic dataset construction.

Builds three behavioral categories -- NORMAL, LEGITIMATE_SHARED_INFRA,
and COORDINATED_ABUSE -- as described in the M1 spec, deliberately
overlapping their signal distributions so no single feature perfectly
separates abuse from non-abuse. See the M1 README for the reasoning
behind each category's parameters.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
from faker import Faker

from scripts.synthetic.behavior import TransactionProfile, sample_amounts, sample_timestamps
from scripts.synthetic.config import GeneratorConfig
from scripts.synthetic.identifiers import device_fingerprint, new_id, private_ip

RETURN_REASONS = [
    "changed_mind",
    "wrong_size",
    "damaged_item",
    "not_as_described",
    "duplicate_order",
    "late_delivery",
]


class SyntheticDataBuilder:
    def __init__(self, config: GeneratorConfig):
        self.config = config
        self.rng = np.random.default_rng(config.random_seed)
        Faker.seed(config.random_seed)
        self.faker = Faker()

        self.merchants: list[dict] = []
        self.customers: list[dict] = []
        self.devices: list[dict] = []
        self.ips: list[dict] = []
        self.customer_device_links: list[dict] = []
        self.customer_network_links: list[dict] = []
        self.transactions: list[dict] = []
        self.orders: list[dict] = []
        self.returns: list[dict] = []
        self.ground_truth: list[dict] = []

        self._merchant_ids: list[str] = []
        self._email_counter = 0
        self._device_registry: dict[str, str] = {}
        self._ip_registry: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    def build(self) -> dict[str, pd.DataFrame]:
        self._build_merchants()
        self._build_normal_customers()
        self._build_shared_infra_clusters()
        self._build_abuse_rings()
        return self._to_frames()

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _random_time_in_window(self):
        start = self.config.window_start()
        end = self.config.window_end
        offset_seconds = self.rng.uniform(0, (end - start).total_seconds())
        return start + timedelta(seconds=float(offset_seconds))

    def _unique_email(self) -> str:
        self._email_counter += 1
        local = f"{self.faker.user_name()}{self._email_counter}"
        return f"{local}@{self.faker.free_email_domain()}"

    def _new_customer_row(self, merchant_id: str, created_at) -> dict:
        row = {
            "id": new_id(self.rng),
            "merchant_id": merchant_id,
            "email": self._unique_email(),
            "display_name": self.faker.name(),
            "created_at": created_at,
        }
        self.customers.append(row)
        return row

    def _new_device(self, created_at=None) -> str:
        # If the randomly generated fingerprint collides with one already
        # issued, it IS the same device by definition -- dedupe rather
        # than violate the unique constraint on device_fingerprint. In
        # practice this mostly happens for the smaller 192.168.x.x IP
        # pool (see _new_ip) and is itself a mildly realistic case of
        # coincidental shared infrastructure between otherwise-unrelated
        # customers.
        fingerprint = device_fingerprint(self.rng)
        existing = self._device_registry.get(fingerprint)
        if existing:
            return existing

        device_id = new_id(self.rng)
        self.devices.append(
            {
                "id": device_id,
                "device_fingerprint": fingerprint,
                "created_at": created_at or self.config.window_start(),
            }
        )
        self._device_registry[fingerprint] = device_id
        return device_id

    def _new_ip(self, created_at=None) -> str:
        ip_address = private_ip(self.rng)
        existing = self._ip_registry.get(ip_address)
        if existing:
            return existing

        ip_id = new_id(self.rng)
        self.ips.append(
            {
                "id": ip_id,
                "ip_address": ip_address,
                "created_at": created_at or self.config.window_start(),
            }
        )
        self._ip_registry[ip_address] = ip_id
        return ip_id

    def _link_device(self, customer_id: str, device_id: str, first_seen, last_seen) -> None:
        self.customer_device_links.append(
            {
                "id": new_id(self.rng),
                "customer_id": customer_id,
                "device_id": device_id,
                "first_seen": first_seen,
                "last_seen": last_seen,
            }
        )

    def _link_ip(self, customer_id: str, ip_id: str, first_seen, last_seen) -> None:
        self.customer_network_links.append(
            {
                "id": new_id(self.rng),
                "customer_id": customer_id,
                "network_id": ip_id,
                "first_seen": first_seen,
                "last_seen": last_seen,
            }
        )

    def _emit_transactions(self, customer_id: str, device_id: str, ip_id: str, profile: TransactionProfile) -> None:
        window_start = profile.account_created_at
        window_end = self.config.window_end
        if window_start >= window_end:
            window_start = window_end - timedelta(hours=1)

        timestamps = sample_timestamps(
            self.rng,
            count=profile.num_transactions,
            window_start=window_start,
            window_end=window_end,
            concentrated=profile.concentrated,
            concentration_days=profile.concentration_days,
        )
        amounts = sample_amounts(
            self.rng,
            count=profile.num_transactions,
            base_amount=profile.base_amount,
            relative_spread=profile.relative_spread,
        )

        for ts, amount in zip(timestamps, amounts):
            tx_id = new_id(self.rng)
            self.transactions.append(
                {
                    "id": tx_id,
                    "customer_id": customer_id,
                    "device_id": device_id,
                    "network_id": ip_id,
                    "amount": amount,
                    "currency": self.config.currency,
                    "status": "success",
                    "created_at": ts,
                }
            )

            order_id = new_id(self.rng)
            order_created_at = ts + timedelta(minutes=int(self.rng.integers(1, 120)))
            self.orders.append(
                {
                    "id": order_id,
                    "transaction_id": tx_id,
                    "order_amount": amount,
                    "created_at": order_created_at,
                }
            )

            if self.rng.random() < profile.return_probability:
                return_created_at = order_created_at + timedelta(days=int(self.rng.integers(1, 14)))
                self.returns.append(
                    {
                        "id": new_id(self.rng),
                        "order_id": order_id,
                        "amount": round(amount * float(self.rng.uniform(0.5, 1.0)), 2),
                        "reason": str(self.rng.choice(RETURN_REASONS)),
                        "created_at": return_created_at,
                    }
                )

    # ------------------------------------------------------------------
    # Category A: NORMAL
    # ------------------------------------------------------------------
    def _build_merchants(self) -> None:
        for _ in range(self.config.merchant_count):
            merchant_id = new_id(self.rng)
            self.merchants.append(
                {
                    "id": merchant_id,
                    "name": self.faker.company(),
                    "created_at": self.config.window_start() - timedelta(days=365),
                }
            )
            self._merchant_ids.append(merchant_id)

    def _build_normal_customers(self) -> None:
        for _ in range(self.config.normal_customer_count):
            created_at = self._random_time_in_window()
            merchant_id = str(self.rng.choice(self._merchant_ids))
            customer = self._new_customer_row(merchant_id, created_at)

            device_id = self._new_device(created_at)
            ip_id = self._new_ip(created_at)
            self._link_device(customer["id"], device_id, created_at, created_at)
            self._link_ip(customer["id"], ip_id, created_at, created_at)

            # A small fraction of ordinary customers get one benign burst
            # of activity (e.g. a sale event) -- this is what creates
            # overlap with the abuse "concentrated window" signal.
            noisy = self.rng.random() < self.config.benign_noise_prob

            profile = TransactionProfile(
                num_transactions=int(self.rng.integers(1, 6)),
                base_amount=float(self.rng.uniform(200, 4000)),
                relative_spread=float(self.rng.uniform(0.3, 0.7)),
                concentrated=noisy,
                concentration_days=float(self.rng.uniform(1, 3)),
                return_probability=float(self.rng.uniform(0.02, 0.12)),
                account_created_at=created_at,
            )
            self._emit_transactions(customer["id"], device_id, ip_id, profile)

            self.ground_truth.append(
                {
                    "customer_id": customer["id"],
                    "label": "normal",
                    "cluster_id": None,
                    "is_abuse": False,
                }
            )

    # ------------------------------------------------------------------
    # Category B: LEGITIMATE SHARED INFRASTRUCTURE
    # ------------------------------------------------------------------
    def _build_shared_infra_clusters(self) -> None:
        remaining = self.config.shared_infra_customer_count
        cluster_index = 0

        while remaining > 0:
            cluster_size = min(
                remaining,
                int(
                    self.rng.integers(
                        self.config.shared_infra_cluster_size_min,
                        self.config.shared_infra_cluster_size_max + 1,
                    )
                ),
            )
            cluster_id = f"shared-infra-{cluster_index:04d}"
            cluster_index += 1

            merchant_id = str(self.rng.choice(self._merchant_ids))
            share_device = self.rng.random() < self.config.shared_infra_share_device_prob
            share_ip = self.rng.random() < self.config.shared_infra_share_ip_prob

            # A genuine household/office builds up its shared infra before
            # everyone joins -- create it up front, not mid-burst.
            shared_device_id = self._new_device() if share_device else None
            shared_ip_id = self._new_ip() if share_ip else None

            # Family/office members join at ordinary, spread-out times --
            # NOT a burst. This is the key contrast with abuse rings.
            creation_times = sorted(self._random_time_in_window() for _ in range(cluster_size))

            for created_at in creation_times:
                customer = self._new_customer_row(merchant_id, created_at)

                own_device_id = shared_device_id or self._new_device(created_at)
                own_ip_id = shared_ip_id or self._new_ip(created_at)
                self._link_device(customer["id"], own_device_id, created_at, created_at)
                self._link_ip(customer["id"], own_ip_id, created_at, created_at)

                # Independent, ordinary shopping behavior -- amounts and
                # timing are NOT coordinated with the rest of the cluster.
                profile = TransactionProfile(
                    num_transactions=int(self.rng.integers(1, 7)),
                    base_amount=float(self.rng.uniform(200, 4000)),
                    relative_spread=float(self.rng.uniform(0.3, 0.7)),
                    concentrated=False,
                    concentration_days=2.0,
                    return_probability=float(self.rng.uniform(0.02, 0.12)),
                    account_created_at=created_at,
                )
                self._emit_transactions(customer["id"], own_device_id, own_ip_id, profile)

                self.ground_truth.append(
                    {
                        "customer_id": customer["id"],
                        "label": "legitimate_shared_infra",
                        "cluster_id": cluster_id,
                        "is_abuse": False,
                    }
                )

            remaining -= cluster_size

    # ------------------------------------------------------------------
    # Category C: COORDINATED ABUSE
    # ------------------------------------------------------------------
    def _build_abuse_rings(self) -> None:
        remaining = self.config.abuse_customer_count
        ring_index = 0

        while remaining > 0:
            ring_size = min(
                remaining,
                int(
                    self.rng.integers(
                        self.config.abuse_ring_size_min, self.config.abuse_ring_size_max + 1
                    )
                ),
            )
            ring_id = f"abuse-ring-{ring_index:04d}"
            ring_index += 1

            # Each ring independently rolls which signals it exhibits, so
            # rings look different from one another and no single signal
            # perfectly predicts abuse across the whole dataset.
            share_device = self.rng.random() < self.config.abuse_share_device_prob
            share_ip = self.rng.random() < self.config.abuse_share_ip_prob
            creation_burst = self.rng.random() < self.config.abuse_creation_burst_prob
            high_velocity = self.rng.random() < self.config.abuse_high_velocity_prob
            similar_amount = self.rng.random() < self.config.abuse_similar_amount_prob
            concentrated_window = self.rng.random() < self.config.abuse_concentrated_window_prob
            high_return = self.rng.random() < self.config.abuse_high_return_prob

            # Most rings target one merchant; some spread across two to
            # avoid per-merchant velocity limits -- also realistic and
            # adds variety the detector will need to generalize across.
            if self.rng.random() < 0.7:
                merchant_choices = [str(self.rng.choice(self._merchant_ids))] * ring_size
            else:
                two = self.rng.choice(self._merchant_ids, size=2, replace=False)
                merchant_choices = [str(self.rng.choice(two)) for _ in range(ring_size)]

            shared_device_id = self._new_device() if share_device else None
            shared_ip_id = self._new_ip() if share_ip else None

            if creation_burst:
                burst_span_hours = float(self.rng.uniform(1, 48))
                start = self.config.window_start()
                end = self.config.window_end - timedelta(hours=burst_span_hours)
                if end <= start:
                    end = start + timedelta(hours=1)
                burst_start = start + timedelta(
                    seconds=float(self.rng.uniform(0, (end - start).total_seconds()))
                )
                creation_times = sorted(
                    burst_start + timedelta(hours=float(h))
                    for h in self.rng.uniform(0, burst_span_hours, size=ring_size)
                )
            else:
                creation_times = sorted(self._random_time_in_window() for _ in range(ring_size))

            ring_base_amount = float(self.rng.uniform(300, 5000))

            for i, created_at in enumerate(creation_times):
                merchant_id = merchant_choices[i]
                customer = self._new_customer_row(merchant_id, created_at)

                # A minority of ring members are "diluted": they still
                # belong to the coordinated scenario (ground truth =
                # abuse) but individually behave close to normal. This
                # keeps the classification problem honest -- not every
                # abusive account is a slam-dunk on its own.
                diluted = self.rng.random() < self.config.abuse_dilution_prob

                own_device_id = (
                    shared_device_id if (share_device and not diluted) else self._new_device(created_at)
                )
                own_ip_id = shared_ip_id if (share_ip and not diluted) else self._new_ip(created_at)
                self._link_device(customer["id"], own_device_id, created_at, created_at)
                self._link_ip(customer["id"], own_ip_id, created_at, created_at)

                if diluted:
                    profile = TransactionProfile(
                        num_transactions=int(self.rng.integers(1, 4)),
                        base_amount=float(self.rng.uniform(200, 4000)),
                        relative_spread=float(self.rng.uniform(0.3, 0.7)),
                        concentrated=False,
                        concentration_days=2.0,
                        return_probability=float(self.rng.uniform(0.02, 0.15)),
                        account_created_at=created_at,
                    )
                else:
                    profile = TransactionProfile(
                        num_transactions=int(self.rng.integers(4, 10))
                        if high_velocity
                        else int(self.rng.integers(1, 4)),
                        base_amount=ring_base_amount
                        if similar_amount
                        else float(self.rng.uniform(200, 5000)),
                        relative_spread=float(self.rng.uniform(0.03, 0.08))
                        if similar_amount
                        else float(self.rng.uniform(0.3, 0.7)),
                        concentrated=concentrated_window,
                        concentration_days=float(self.rng.uniform(0.5, 2.0)),
                        return_probability=float(self.rng.uniform(0.4, 0.8))
                        if high_return
                        else float(self.rng.uniform(0.05, 0.15)),
                        account_created_at=created_at,
                    )

                self._emit_transactions(customer["id"], own_device_id, own_ip_id, profile)

                self.ground_truth.append(
                    {
                        "customer_id": customer["id"],
                        "label": "coordinated_abuse",
                        "cluster_id": ring_id,
                        "is_abuse": True,
                    }
                )

            remaining -= ring_size

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    def _to_frames(self) -> dict[str, pd.DataFrame]:
        return {
            "merchants": pd.DataFrame(self.merchants),
            "customers": pd.DataFrame(self.customers),
            "devices": pd.DataFrame(self.devices),
            "ips": pd.DataFrame(self.ips),
            "customer_device_links": pd.DataFrame(self.customer_device_links),
            "customer_network_links": pd.DataFrame(self.customer_network_links),
            "transactions": pd.DataFrame(self.transactions),
            "orders": pd.DataFrame(self.orders),
            "returns": pd.DataFrame(self.returns),
            "ground_truth": pd.DataFrame(self.ground_truth),
        }
