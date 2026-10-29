"""Provider di dati di riferimento per le regole di validazione.

Implementazione dell'interfaccia ReferenceDataProvider che può essere
configurata con dati da diverse sorgenti (JSON sintetici, database, API).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SyntheticReferenceDataProvider:
    """Provider che carica dati dai file JSON sintetici.
    
    Carica clienti da synthetic/data/customers.json e
    catalogo da synthetic/data/catalog.json.
    """
    
    def __init__(
        self,
        customers_path: Path | str | None = None,
        catalog_path: Path | str | None = None,
    ) -> None:
        self._customers: list[dict[str, Any]] = []
        self._catalog: list[dict[str, Any]] = []
        self._customers_by_id: dict[int, dict[str, Any]] = {}
        self._customers_by_domain: dict[str, dict[str, Any]] = {}
        self._products_by_id: dict[int, dict[str, Any]] = {}
        self._products_by_sku: dict[str, dict[str, Any]] = {}
        self._xrefs: dict[str, dict[str, Any]] = {}
        self._order_history: list[dict[str, Any]] = []
        
        if customers_path:
            self.load_customers(customers_path)
        if catalog_path:
            self.load_catalog(catalog_path)
    
    def load_customers(self, path: Path | str) -> None:
        """Carica i clienti da un file JSON."""
        with open(path) as f:
            self._customers = json.load(f)
        
        for customer in self._customers:
            partner_id = customer.get("erp_partner_id")
            if partner_id:
                self._customers_by_id[partner_id] = customer
            
            domain = customer.get("email_domain", "").lower()
            if domain:
                self._customers_by_domain[domain] = customer
            
            for xref in customer.get("xref", []):
                key = f"{customer.get('erp_partner_id')}:{xref.get('customer_code', '').upper()}"
                self._xrefs[key] = {
                    **xref,
                    "partner_id": partner_id,
                }
    
    def load_catalog(self, path: Path | str) -> None:
        """Carica il catalogo prodotti da un file JSON."""
        with open(path) as f:
            self._catalog = json.load(f)
        
        for product in self._catalog:
            product_id = product.get("erp_product_id")
            if product_id:
                self._products_by_id[product_id] = product
            
            sku = product.get("sku", "").upper()
            if sku:
                self._products_by_sku[sku] = product
    
    def add_order_history(self, orders: list[dict[str, Any]]) -> None:
        """Aggiunge ordini allo storico."""
        self._order_history.extend(orders)
    
    def get_customer_by_id(self, partner_id: int) -> dict[str, Any] | None:
        """Recupera un cliente per ID ERP."""
        return self._customers_by_id.get(partner_id)
    
    def get_customer_by_email_domain(self, domain: str) -> dict[str, Any] | None:
        """Recupera un cliente per dominio email."""
        return self._customers_by_domain.get(domain.lower())
    
    def get_product_by_id(self, product_id: int) -> dict[str, Any] | None:
        """Recupera un prodotto per ID ERP."""
        return self._products_by_id.get(product_id)
    
    def get_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        """Recupera un prodotto per SKU."""
        return self._products_by_sku.get(sku.upper())
    
    def get_xref(
        self, tenant_id: str, partner_id: int, customer_code: str
    ) -> dict[str, Any] | None:
        """Recupera cross-reference cliente-articolo."""
        key = f"{partner_id}:{customer_code.upper()}"
        return self._xrefs.get(key)
    
    def get_customer_ship_to_addresses(self, partner_id: int) -> list[dict[str, Any]]:
        """Recupera gli indirizzi di consegna di un cliente."""
        customer = self._customers_by_id.get(partner_id)
        if customer:
            return customer.get("ship_to", [])
        return []
    
    def get_order_history(
        self, tenant_id: str, partner_id: int, po_number: str
    ) -> list[dict[str, Any]]:
        """Recupera lo storico ordini per controllo duplicati."""
        results = []
        for order in self._order_history:
            order_partner = order.get("partner_id")
            order_po = order.get("po_number")
            
            if partner_id and order_partner != partner_id:
                continue
            
            if po_number and order_po != po_number:
                continue
            
            results.append(order)
        
        return results
    
    def get_product_history_stats(
        self, tenant_id: str, partner_id: int, product_id: int
    ) -> dict[str, Any] | None:
        """Recupera le statistiche storiche di un prodotto per un cliente."""
        return None


class MockReferenceDataProvider:
    """Provider mock per i test unitari."""
    
    def __init__(self) -> None:
        self.customers: dict[int, dict[str, Any]] = {}
        self.products: dict[int, dict[str, Any]] = {}
        self.ship_to_addresses: dict[int, list[dict[str, Any]]] = {}
        self.order_history: list[dict[str, Any]] = []
        self.product_stats: dict[str, dict[str, Any]] = {}
    
    def add_customer(self, partner_id: int, data: dict[str, Any]) -> None:
        """Aggiunge un cliente mock."""
        self.customers[partner_id] = data
    
    def add_product(self, product_id: int, data: dict[str, Any]) -> None:
        """Aggiunge un prodotto mock."""
        self.products[product_id] = data
    
    def get_customer_by_id(self, partner_id: int) -> dict[str, Any] | None:
        return self.customers.get(partner_id)
    
    def get_customer_by_email_domain(self, domain: str) -> dict[str, Any] | None:
        for customer in self.customers.values():
            if customer.get("email_domain", "").lower() == domain.lower():
                return customer
        return None
    
    def get_product_by_id(self, product_id: int) -> dict[str, Any] | None:
        return self.products.get(product_id)
    
    def get_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        for product in self.products.values():
            if product.get("sku", "").upper() == sku.upper():
                return product
        return None
    
    def get_xref(
        self, tenant_id: str, partner_id: int, customer_code: str
    ) -> dict[str, Any] | None:
        return None
    
    def get_customer_ship_to_addresses(self, partner_id: int) -> list[dict[str, Any]]:
        return self.ship_to_addresses.get(partner_id, [])
    
    def get_order_history(
        self, tenant_id: str, partner_id: int, po_number: str
    ) -> list[dict[str, Any]]:
        return [
            o for o in self.order_history
            if (not partner_id or o.get("partner_id") == partner_id) and
               (not po_number or o.get("po_number") == po_number)
        ]
    
    def get_product_history_stats(
        self, tenant_id: str, partner_id: int, product_id: int
    ) -> dict[str, Any] | None:
        key = f"{partner_id}:{product_id}"
        return self.product_stats.get(key)
