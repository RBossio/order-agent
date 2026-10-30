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
