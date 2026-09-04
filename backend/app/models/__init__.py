"""Import all ORM models so they register on `Base.metadata`.

Anything that needs to create tables (e.g. `init_db.py`, Alembic in a
future milestone) should import this package first.
"""

from app.models.customer import Customer
from app.models.device import Device
from app.models.ground_truth import GroundTruth, GroundTruthLabel
from app.models.links import CustomerDeviceLink, CustomerNetworkLink
from app.models.merchant import Merchant
from app.models.network_identifier import NetworkIdentifier
from app.models.order import Order
from app.models.return_ import Return
from app.models.transaction import Transaction, TransactionStatus

__all__ = [
    "Merchant",
    "Customer",
    "Device",
    "NetworkIdentifier",
    "CustomerDeviceLink",
    "CustomerNetworkLink",
    "Transaction",
    "TransactionStatus",
    "Order",
    "Return",
    "GroundTruth",
    "GroundTruthLabel",
]
