"""Financial exposure calculation.

Answers "how much financial activity is associated with this candidate
cluster?" -- NOT "how much money was lost to fraud". See
`models.ExposureAssessment` for the terminology this module commits to
and why. Uses M1's transaction/order/return tables directly (via the
M2 `RawData` already loaded for the pipeline); no new data source.
"""

from __future__ import annotations

from app.intelligence.data_loader import RawData
from app.risk.models import ExposureAssessment


def compute_exposure(transaction_ids: list[str], data: RawData) -> ExposureAssessment:
    """Compute exposure for one cluster from its M2-derived transaction ID list."""
    if not transaction_ids:
        return ExposureAssessment(
            transaction_count=0,
            transaction_value=0.0,
            order_count=0,
            return_count=0,
            returned_value=0.0,
            estimated_exposure=0.0,
        )

    tx = data.transactions[data.transactions["id"].isin(transaction_ids)]
    orders = data.orders[data.orders["transaction_id"].isin(transaction_ids)]
    returns = data.returns[data.returns["order_id"].isin(orders["id"])]

    transaction_value = float(tx["amount"].sum()) if not tx.empty else 0.0
    returned_value = float(returns["amount"].sum()) if not returns.empty else 0.0

    return ExposureAssessment(
        transaction_count=len(tx),
        transaction_value=round(transaction_value, 2),
        order_count=len(orders),
        return_count=len(returns),
        returned_value=round(returned_value, 2),
        # Returned value is the only amount that has actually reversed --
        # deliberately NOT the full transaction value. See module docstring
        # and ExposureAssessment.estimated_exposure for why this is not
        # framed as a fraud-loss figure.
        estimated_exposure=round(returned_value, 2),
    )
