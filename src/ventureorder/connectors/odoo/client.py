"""Interfaccia sostituibile verso l'API esterna di Odoo."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any


class OdooClient(ABC):
    """Contratto minimo usato dal connettore.

    Le implementazioni reali parlano JSON-RPC, XML-RPC o JSON-2.
    I test unitari usano :class:`FakeOdooClient` senza un server Odoo.
    """

    @property
    @abstractmethod
    def major_version(self) -> int:
        """Major version del server (es. 19)."""

    @abstractmethod
    def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str] | None = None,
        *,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        """Cerca e legge record."""

    @abstractmethod
    def search_count(self, model: str, domain: list[Any]) -> int:
        """Conta i record che soddisfano il dominio."""

    @abstractmethod
    def create(self, model: str, values: dict[str, Any]) -> int:
        """Crea un record e restituisce l'id."""

    @abstractmethod
    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Legge i record per id."""

    @abstractmethod
    def unlink(self, model: str, ids: list[int]) -> bool:
        """Elimina i record (usato dai test di integrazione per il cleanup)."""


def create_client(
    url: str,
    db: str,
    username: str,
    password: str,
    *,
    transport: str = "jsonrpc",
    timeout: float = 30.0,
    major_version: int | None = None,
) -> OdooClient:
    """Fabbrica del client Odoo.

    Args:
        url: URL base (es. ``http://localhost:8069``).
        db: Nome database.
        username: Login o utente tecnico.
        password: Password o chiave API (per JSON-RPC/XML-RPC).
        transport: ``jsonrpc`` (default), ``xmlrpc`` o ``json2``.
        timeout: Timeout HTTP in secondi.
        major_version: Forza la major version (utile per JSON-2).
    """
    name = (transport or "jsonrpc").strip().lower()
    if name == "jsonrpc":
        from ventureorder.connectors.odoo.rpc import JsonRpcOdooClient

        return JsonRpcOdooClient(url, db, username, password, timeout=timeout)
    if name == "xmlrpc":
        from ventureorder.connectors.odoo.rpc import XmlRpcOdooClient

        return XmlRpcOdooClient(url, db, username, password, timeout=timeout)
    if name == "json2":
        from ventureorder.connectors.odoo.rpc import Json2OdooClient

        return Json2OdooClient(
            url,
            db,
            password,
            timeout=timeout,
            major_version=major_version or 19,
        )
    if name == "fake":
        from ventureorder.connectors.odoo.fake import FakeOdooClient

        return FakeOdooClient(major_version=major_version or 19)
    raise ValueError(f"Trasporto Odoo sconosciuto: {transport!r}")


def client_from_env(*, transport: str | None = None) -> OdooClient:
    """Crea un client dalle variabili d'ambiente già usate dal repo.

    Variabili: ``ODOO_URL``, ``ODOO_DB``, ``ODOO_USER``,
    ``ODOO_PASSWORD`` / ``ODOO_ADMIN_PASSWORD`` / ``ODOO_API_KEY``,
    ``ODOO_TRANSPORT``.
    """
    url = os.environ.get("ODOO_URL", "http://localhost:8069")
    db = os.environ.get("ODOO_DB", "vo_demo")
    username = os.environ.get("ODOO_USER", "admin")
    password = (
        os.environ.get("ODOO_PASSWORD")
        or os.environ.get("ODOO_API_KEY")
        or os.environ.get("ODOO_ADMIN_PASSWORD")
        or ""
    )
    chosen = transport or os.environ.get("ODOO_TRANSPORT") or "jsonrpc"
    return create_client(url, db, username, password, transport=chosen)
