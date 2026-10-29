"""Reference data providers for validation rules."""

from typing import Any


class SyntheticReferenceDataProvider:
    """Reference data provider using synthetic/generated data."""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = data_dir
        self._customers: dict[str, dict[str, Any]] = {}
        self._items: dict[str, dict[str, Any]] = {}
        self._xrefs: dict[str, dict[str, Any]] = {}
        self._orders: list[dict[str, Any]] = []

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        return self._customers.get(customer_id)

    def get_customer_by_name(self, name: str) -> list[dict[str, Any]]:
        name_lower = name.lower()
        return [c for c in self._customers.values() if name_lower in c.get("name", "").lower()]

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        return self._items.get(item_id)

    def get_item_by_code(self, code: str) -> list[dict[str, Any]]:
        results = []
        for item in self._items.values():
            if code in (item.get("gtin"), item.get("mpn"), item.get("sku")):
                results.append(item)
        return results

    def get_customer_item_xref(
        self, customer_id: str, customer_item_code: str
    ) -> dict[str, Any] | None:
        key = f"{customer_id}:{customer_item_code}"
        return self._xrefs.get(key)

    def get_existing_orders(
        self, customer_id: str, po_number: str
    ) -> list[dict[str, Any]]:
        return [
            o
            for o in self._orders
            if o.get("customer_id") == customer_id and o.get("po_number") == po_number
        ]

    def get_similar_orders(
        self, customer_id: str, order_date: str, total: float
    ) -> list[dict[str, Any]]:
        return []

    def get_order_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        for order in self._orders:
            if order.get("content_hash") == content_hash:
                return order
        return None

    def get_uom_conversion(
        self, from_uom: str, to_uom: str, item_id: str | None = None
    ) -> float | None:
        conversions = {
            ("PZ", "EA"): 1.0,
            ("EA", "PZ"): 1.0,
            ("KG", "G"): 1000.0,
            ("G", "KG"): 0.001,
            ("M", "CM"): 100.0,
            ("CM", "M"): 0.01,
            ("L", "ML"): 1000.0,
            ("ML", "L"): 0.001,
            ("CT", "PZ"): 12.0,
            ("PZ", "CT"): 1 / 12.0,
        }
        return conversions.get((from_uom.upper(), to_uom.upper()))

    def is_valid_uom(self, uom: str) -> bool:
        valid_uoms = {
            "PZ", "EA", "UN", "KG", "G", "L", "ML", "M", "CM", "MM",
            "CT", "BOX", "PAL", "PKG", "SET", "PR", "DZ", "GR", "MTR",
        }
        return uom.upper() in valid_uoms

    def get_item_price(
        self, item_id: str, customer_id: str | None = None
    ) -> float | None:
        item = self._items.get(item_id)
        if item:
            return item.get("price")
        return None

    def is_valid_currency(self, currency: str) -> bool:
        valid_currencies = {"EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD"}
        return currency.upper() in valid_currencies

    def is_dangerous_extension(self, extension: str) -> bool:
        dangerous = {
            ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".pif",
            ".vbs", ".js", ".jar", ".ps1", ".sh", ".dll", ".sys",
        }
        return extension.lower() in dangerous

    def get_peppol_endpoint(self, customer_id: str) -> str | None:
        customer = self._customers.get(customer_id)
        if customer:
            return customer.get("peppol_endpoint")
        return None

    def get_peppol_uom_codes(self) -> set[str]:
        return {
            "C62", "EA", "KGM", "GRM", "LTR", "MTR", "CMT", "MMT",
            "MTK", "MTQ", "LBR", "ONZ", "GLL", "QT", "PT", "INH",
        }


class MockReferenceDataProvider(SyntheticReferenceDataProvider):
    """Mock provider for testing with configurable responses."""

    def __init__(self) -> None:
        super().__init__()
        self._mock_responses: dict[str, Any] = {}

    def set_mock(self, method: str, response: Any) -> None:
        """Set a mock response for a method."""
        self._mock_responses[method] = response

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        if "get_customer" in self._mock_responses:
            return self._mock_responses["get_customer"]
        return super().get_customer(customer_id)

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        if "get_item" in self._mock_responses:
            return self._mock_responses["get_item"]
        return super().get_item(item_id)

    def get_existing_orders(
        self, customer_id: str, po_number: str
    ) -> list[dict[str, Any]]:
        if "get_existing_orders" in self._mock_responses:
            return self._mock_responses["get_existing_orders"]
        return super().get_existing_orders(customer_id, po_number)

    def get_order_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        if "get_order_by_hash" in self._mock_responses:
            return self._mock_responses["get_order_by_hash"]
        return super().get_order_by_hash(content_hash)

    def get_similar_orders(
        self, customer_id: str, order_date: str, total: float
    ) -> list[dict[str, Any]]:
        if "get_similar_orders" in self._mock_responses:
            return self._mock_responses["get_similar_orders"]
        return super().get_similar_orders(customer_id, order_date, total)

    def get_customer_item_xref(
        self, customer_id: str, customer_item_code: str
    ) -> dict[str, Any] | None:
        if "get_customer_item_xref" in self._mock_responses:
            return self._mock_responses["get_customer_item_xref"]
        return super().get_customer_item_xref(customer_id, customer_item_code)

    def get_item_price(
        self, item_id: str, customer_id: str | None = None
    ) -> float | None:
        if "get_item_price" in self._mock_responses:
            return self._mock_responses["get_item_price"]
        return super().get_item_price(item_id, customer_id)

    def get_peppol_endpoint(self, customer_id: str) -> str | None:
        if "get_peppol_endpoint" in self._mock_responses:
            return self._mock_responses["get_peppol_endpoint"]
        return super().get_peppol_endpoint(customer_id)
