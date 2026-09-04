"""Dataset-wide baselines used to contextualize per-cluster signals.

Computed once per pipeline run (not per cluster) since they're global
aggregates -- recomputing them per cluster would be wasted O(clusters
x dataset_size) work for numbers that don't change between clusters.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.intelligence.data_loader import RawData


@dataclass
class GlobalBaselines:
    global_return_rate: float
    avg_transactions_per_customer: float


def compute_global_baselines(data: RawData) -> GlobalBaselines:
    num_orders = len(data.orders)
    num_returns = len(data.returns)
    global_return_rate = (num_returns / num_orders) if num_orders > 0 else 0.0

    num_customers = len(data.customers)
    num_transactions = len(data.transactions)
    avg_tx_per_customer = (num_transactions / num_customers) if num_customers > 0 else 0.0

    return GlobalBaselines(
        global_return_rate=global_return_rate,
        avg_transactions_per_customer=avg_tx_per_customer,
    )
