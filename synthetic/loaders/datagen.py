"""Loader adattatore per datagen/master/.

Carica i dati master da datagen/master/ (products.json, customers.json,
customer_xref.json) e li trasforma nel formato atteso dal generatore sintetico.

Mappatura campi prodotti:
    sku ← default_code
    description ← name
    uom ← sale_uom
    price ← list_price
    category ← category
    gtin ← gtin
    manufacturer_part_number ← manufacturer_code
    manufacturer_name ← manufacturer_name
    pack ← costruito da pack_description e conversions

Mappatura campi clienti:
    customer_id ← ref
    erp_partner_ref ← ref
    name ← name
    tax_id ← tax_id
    contact ← {email, phone}
    email_domain ← estratto da email
    address ← billing_address
    ship_to ← shipping_addresses con codici SHIP-01, SHIP-02, ...

Mappatura xref:
    customer_code ← customer_item_code
    sku ← product_sku
    uom ← customer_uom
    status ← TRUSTED
"""

import json
from pathlib import Path
from typing import Any


class DatagenLoader:
    """Loader che carica da datagen/master/ e adatta i dati.

    Trasforma i dati dal formato datagen (products.json, customers.json,
    customer_xref.json) al formato atteso dal generatore sintetico.
    """

    def __init__(self, datagen_path: Path, profiles_path: Path | None = None):
        """Inizializza il loader.

        Args:
            datagen_path: Percorso a datagen/master/
            profiles_path: Percorso a synthetic/profiles/order_styles.json
        """
        self.datagen_path = datagen_path
        self.profiles_path = profiles_path or (
            Path(__file__).parent.parent / "profiles" / "order_styles.json"
        )
        self._validate_path()
        self._order_styles: dict[str, dict] | None = None

    def _validate_path(self) -> None:
        """Verifica che i file necessari esistano."""
        required_files = ["products.json", "customers.json", "customer_xref.json"]
        for fname in required_files:
            fpath = self.datagen_path / fname
            if not fpath.exists():
                raise FileNotFoundError(
                    f"File {fpath} non trovato. "
                    f"Assicurati che datagen/master/ contenga i dati master."
                )

    def _load_order_styles(self) -> dict[str, dict]:
        """Carica gli stili ordine dal profilo esterno."""
        if self._order_styles is not None:
            return self._order_styles

        if self.profiles_path.exists():
            with open(self.profiles_path, encoding="utf-8") as f:
                self._order_styles = json.load(f)
        else:
            self._order_styles = {}

        return self._order_styles

    def _parse_pack(
        self,
        pack_description: str | None,
        sale_uom: str,
        conversions: list[dict]
    ) -> dict[str, Any] | None:
        """Converte pack_description e conversions nel formato pack del generatore.

        Args:
            pack_description: Descrizione pack (es. "BX/50", "4/1GAL", "100/BX 10BX/CS")
            sale_uom: UoM di vendita
            conversions: Lista conversioni dal prodotto datagen

        Returns:
            Dizionario pack con raw, inner_count, inner_size, inner_uom o None
        """
        if not pack_description:
            return None

        conv_map = {(c["from_uom"], c["to_uom"]): c["factor"] for c in conversions}

        inner_count = 1
        inner_size = 1
        inner_uom = "EA"

        if sale_uom in conv_map.get((sale_uom,), {}) or conversions:
            for conv in conversions:
                if conv["from_uom"] == sale_uom:
                    inner_count = int(conv["factor"])
                    inner_uom = conv["to_uom"]
                    break

        for conv in conversions:
            if conv["from_uom"] == sale_uom:
                inner_count = int(conv["factor"])
                inner_uom = conv["to_uom"]
                break

        return {
            "raw": pack_description,
            "inner_count": inner_count,
            "inner_size": inner_size,
            "inner_uom": inner_uom
        }

    def load_catalog(self, output_path: Path | None = None) -> list[dict[str, Any]]:
        """Carica il catalogo da datagen/master/products.json e lo adatta.

        Mappatura:
            sku ← default_code
            description ← name
            uom ← sale_uom
            price ← list_price
            category ← category
            gtin ← gtin
            manufacturer_part_number ← manufacturer_code
            manufacturer_name ← manufacturer_name
            pack ← costruito da pack_description + conversions
            erp_product_id ← indice + 1000

        Args:
            output_path: Se specificato, salva il catalogo trasformato.

        Returns:
            Lista di articoli nel formato del generatore sintetico.
        """
        products_path = self.datagen_path / "products.json"
        with open(products_path, encoding="utf-8") as f:
            products = json.load(f)

        catalog = []
        for idx, prod in enumerate(products):
            pack = self._parse_pack(
                prod.get("pack_description"),
                prod["sale_uom"],
                prod.get("conversions", [])
            )

            item = {
                "sku": prod["default_code"],
                "description": prod["name"],
                "uom": prod["sale_uom"],
                "pack": pack,
                "price": prod["list_price"],
                "erp_product_id": 1000 + idx,
                "category": prod.get("category", "MISC"),
                "gtin": prod.get("gtin"),
                "manufacturer_part_number": prod.get("manufacturer_code"),
                "manufacturer_name": prod.get("manufacturer_name"),
                "conversions": [
                    {
                        "from_uom": conv["from_uom"],
                        "to_uom": conv["to_uom"],
                        "factor": conv["factor"],
                    }
                    for conv in prod.get("conversions", [])
                    if conv.get("from_uom") and conv.get("to_uom") and conv.get("factor")
                ],
            }
            catalog.append(item)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(catalog, f, indent=2, ensure_ascii=False)

        return catalog

    def _extract_email_domain(self, email: str) -> str:
        """Estrae il dominio da un indirizzo email."""
        if "@" in email:
            return email.split("@")[1]
        return "example.com"

    def load_customers(
        self,
        catalog: list[dict[str, Any]],
        output_path: Path | None = None
    ) -> list[dict[str, Any]]:
        """Carica i clienti da datagen/master/ e li adatta con xref.

        Mappatura:
            customer_id ← ref
            erp_partner_id ← indice * 3 + 42
            erp_partner_ref ← ref
            name ← name
            tax_id ← tax_id (prefisso US)
            email_domain ← estratto da email
            contact ← {name: da pricelist_name, email, phone}
            address ← billing_address
            ship_to ← shipping_addresses con codici SHIP-01, SHIP-02, ...
            order_style ← da profiles/order_styles.json
            xref_coverage ← da profiles/order_styles.json
            xref ← da customer_xref.json

        Args:
            catalog: Catalogo articoli per validare xref.
            output_path: Se specificato, salva i clienti trasformati.

        Returns:
            Lista di clienti nel formato del generatore sintetico.
        """
        customers_path = self.datagen_path / "customers.json"
        with open(customers_path, encoding="utf-8") as f:
            raw_customers = json.load(f)

        xref_path = self.datagen_path / "customer_xref.json"
        with open(xref_path, encoding="utf-8") as f:
            raw_xrefs = json.load(f)

        sku_set = {item["sku"] for item in catalog}
        sku_to_item = {item["sku"]: item for item in catalog}

        order_styles = self._load_order_styles()

        xref_by_customer: dict[str, list[dict]] = {}
        for xref in raw_xrefs:
            cust_ref = xref["customer_ref"]
            if cust_ref not in xref_by_customer:
                xref_by_customer[cust_ref] = []
            xref_by_customer[cust_ref].append(xref)

        customers = []
        for idx, cust in enumerate(raw_customers):
            ref = cust["ref"]
            email = cust.get("email", f"purchasing@{ref.lower()}.example")

            contact_name = f"Purchasing Dept ({cust['name'].split()[0]})"
            if cust.get("pricelist_name"):
                contact_name = f"{cust['pricelist_name'].replace(' Pricelist', '')} Purchasing"

            ship_to_list = []
            for ship_idx, ship_addr in enumerate(cust.get("shipping_addresses", []), 1):
                ship_code = f"SHIP-{ship_idx:02d}"
                ship_name = f"{cust['name'].split()[0]} Shipping Location {ship_idx}"
                ship_to_list.append({
                    "code": ship_code,
                    "name": ship_name,
                    "address": ship_addr
                })

            if not ship_to_list:
                ship_to_list = [{
                    "code": "SHIP-01",
                    "name": f"{cust['name'].split()[0]} Main",
                    "address": cust.get("billing_address", {})
                }]

            style_data = order_styles.get(ref, {})
            order_style = style_data.get("order_style", {
                "format_preference": ["PDF", "XLSX"],
                "po_prefix": ref.replace("C-", "") + "-",
                "date_format": "YYYY-MM-DD",
                "uses_own_codes": True,
                "code_prefix": ref.replace("C-", "") + "-",
                "typical_lines": [3, 8],
                "currency": "USD",
                "language": "en"
            })
            xref_coverage = style_data.get("xref_coverage", 0.7)

            cust_xrefs = xref_by_customer.get(ref, [])
            validated_xrefs = []
            for xref in cust_xrefs:
                sku = xref["product_sku"]
                if sku in sku_set:
                    validated_xrefs.append({
                        "customer_code": xref["customer_item_code"],
                        "sku": sku,
                        "erp_product_id": sku_to_item[sku]["erp_product_id"],
                        "uom": xref.get("customer_uom"),
                        "status": "TRUSTED"
                    })

            tax_id = cust.get("tax_id", "")
            if tax_id and not tax_id.startswith("US"):
                tax_id = f"US{tax_id}"

            customer = {
                "customer_id": ref,
                "name": cust["name"],
                "tax_id": tax_id,
                "erp_partner_id": idx * 3 + 42,
                "erp_partner_ref": ref,
                "email_domain": self._extract_email_domain(email),
                "contact": {
                    "name": contact_name,
                    "email": email,
                    "phone": cust.get("phone", "+1-555-0000")
                },
                "address": cust.get("billing_address", {}),
                "ship_to": ship_to_list,
                "order_style": order_style,
                "xref_coverage": xref_coverage,
                "xref": validated_xrefs
            }
            customers.append(customer)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(customers, f, indent=2, ensure_ascii=False)

        return customers
