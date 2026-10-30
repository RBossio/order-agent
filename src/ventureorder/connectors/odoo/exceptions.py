"""Eccezioni del connettore Odoo."""

from __future__ import annotations


class OdooConnectorError(Exception):
    """Errore di base del connettore Odoo."""


class OdooTransientError(OdooConnectorError):
    """Errore transitorio (rete, timeout, HTTP 5xx). Si può ritentare."""


class OdooAuthError(OdooConnectorError):
    """Autenticazione fallita o chiave API scaduta. Nessun retry."""


class OdooDataError(OdooConnectorError):
    """Errore sui dati (validazione Odoo, VOF incompleto). Nessun retry."""


class CustomerNotFoundError(OdooDataError):
    """Il cliente risolto non esiste in Odoo o manca dal VOF."""


class ProductNotFoundError(OdooDataError):
    """Un prodotto di riga non esiste in Odoo o non è stato risolto."""


class DuplicatePurchaseOrderError(OdooDataError):
    """Esiste già un ``sale.order`` non annullato con lo stesso PO e cliente (DUP-01).

    Non è riconciliazione: l'ordine Odoo trovato ha un ``origin`` diverso da
    ``VO:<order_id>`` del VOF in ingresso. Il chiamante non deve marcare POSTED.
    """

    def __init__(
        self,
        message: str,
        *,
        odoo_id: int,
        name: str = "",
        origin: str = "",
        client_order_ref: str = "",
    ) -> None:
        super().__init__(message)
        self.odoo_id = odoo_id
        self.name = name
        self.origin = origin
        self.client_order_ref = client_order_ref
