"""Connettore Odoo: VOF → bozza ``sale.order``.

L'API esterna (JSON-RPC, XML-RPC o JSON-2) sta dietro :class:`OdooClient`.
I test unitari usano :class:`FakeOdooClient` e non richiedono Odoo.
"""

from ventureorder.connectors.odoo.client import OdooClient, client_from_env, create_client
from ventureorder.connectors.odoo.connector import OdooSaleOrderConnector, PostedSaleOrder
from ventureorder.connectors.odoo.exceptions import (
    CustomerNotFoundError,
    DuplicatePurchaseOrderError,
    OdooAuthError,
    OdooConnectorError,
    OdooDataError,
    OdooTransientError,
    ProductNotFoundError,
)
from ventureorder.connectors.odoo.fake import FakeOdooClient
from ventureorder.connectors.odoo.rpc import (
    Json2OdooClient,
    JsonRpcOdooClient,
    XmlRpcOdooClient,
    is_odoo_available,
)

__all__ = [
    "CustomerNotFoundError",
    "DuplicatePurchaseOrderError",
    "FakeOdooClient",
    "Json2OdooClient",
    "JsonRpcOdooClient",
    "OdooAuthError",
    "OdooClient",
    "OdooConnectorError",
    "OdooDataError",
    "OdooSaleOrderConnector",
    "OdooTransientError",
    "PostedSaleOrder",
    "ProductNotFoundError",
    "XmlRpcOdooClient",
    "client_from_env",
    "create_client",
    "is_odoo_available",
]
