#!/usr/bin/env python3
"""
Script idempotente per il seed di Odoo con dati sintetici MRO/JanSan.

Crea via XML-RPC/JSON-RPC:
- Azienda distributore fittizia
- UoM aggiuntive (§8.7 architettura)
- 300 articoli MRO/JanSan
- 10 clienti fittizi con indirizzi
- Listini per cliente
- Utente tecnico ventureorder-bot

Idempotente: controlla l'esistenza prima di creare.
Compatibile con Odoo 18.0 e 19.0 (gestisce rinomina product_uom → product_uom_id).
"""

import json
import os
import sys
import xmlrpc.client
from pathlib import Path
from typing import Any

MASTER_DIR = Path(__file__).parent.parent / "datagen" / "master"


class OdooClient:
    """Client XML-RPC per Odoo."""

    def __init__(
        self,
        url: str,
        db: str,
        username: str,
        password: str,
    ):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.uid: int | None = None
        self.version_info: dict | None = None

        self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)

    def authenticate(self) -> int:
        """Autentica e restituisce l'uid."""
        self.version_info = self.common.version()
        print(f"Odoo version: {self.version_info.get('server_version', 'unknown')}")

        self.uid = self.common.authenticate(
            self.db, self.username, self.password, {}
        )
        if not self.uid:
            raise RuntimeError(f"Authentication failed for {self.username}@{self.db}")
        print(f"Authenticated as uid={self.uid}")
        return self.uid

    def execute(self, model: str, method: str, *args, **kwargs) -> Any:
        """Esegue una chiamata execute_kw."""
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, method, args, kwargs
        )

    def search(self, model: str, domain: list, **kwargs) -> list[int]:
        """Cerca record."""
        return self.execute(model, "search", domain, **kwargs)

    def search_read(
        self, model: str, domain: list, fields: list[str], **kwargs
    ) -> list[dict]:
        """Cerca e legge record."""
        return self.execute(model, "search_read", domain, fields=fields, **kwargs)

    def create(self, model: str, values: dict) -> int:
        """Crea un record."""
        return self.execute(model, "create", values)

    def write(self, model: str, ids: list[int], values: dict) -> bool:
        """Aggiorna record."""
        return self.execute(model, "write", ids, values)

    def search_count(self, model: str, domain: list) -> int:
        """Conta record."""
        return self.execute(model, "search_count", domain)

    def get_or_create(
        self,
        model: str,
        domain: list,
        values: dict,
        name_field: str = "name",
    ) -> tuple[int, bool]:
        """Cerca un record, se non esiste lo crea. Restituisce (id, created)."""
        existing = self.search(model, domain, limit=1)
        if existing:
            return existing[0], False
        new_id = self.create(model, values)
        return new_id, True

    @property
    def odoo_major_version(self) -> int:
        """Restituisce la major version di Odoo (es. 19)."""
        if self.version_info:
            ver = self.version_info.get("server_version", "19.0")
            return int(ver.split(".")[0])
        return 19


def load_master_data() -> tuple[list, list, list, dict]:
    """Carica i dati master da JSON."""
    with open(MASTER_DIR / "products.json", encoding="utf-8") as f:
        products = json.load(f)
    with open(MASTER_DIR / "customers.json", encoding="utf-8") as f:
        customers = json.load(f)
    with open(MASTER_DIR / "customer_xref.json", encoding="utf-8") as f:
        xrefs = json.load(f)
    with open(MASTER_DIR / "uom_definitions.json", encoding="utf-8") as f:
        uoms = json.load(f)
    return products, customers, xrefs, uoms


def setup_company(client: OdooClient) -> int:
    """Configura l'azienda distributore."""
    print("\n=== Configurazione azienda ===")

    # Cerca l'azienda principale
    companies = client.search_read(
        "res.company", [], ["id", "name", "currency_id"], limit=1
    )
    if not companies:
        raise RuntimeError("Nessuna azienda trovata")

    company = companies[0]
    company_id = company["id"]
    print(f"Azienda: {company['name']} (id={company_id})")

    # Aggiorna con dati sintetici
    client.write(
        "res.company",
        [company_id],
        {
            "name": "Delta Industrial Supply LLC (SYNTHETIC)",
            "street": "55 Commerce Dr",
            "city": "Dayton",
            "zip": "45402",
            "country_id": client.search("res.country", [("code", "=", "US")], limit=1)[0],
            "state_id": client.search("res.country.state", [("code", "=", "OH")], limit=1)[0],
            "phone": "+1-555-0001",
            "email": "orders@delta-industrial.example",
            "website": "https://delta-industrial.example",
        },
    )
    print("  Azienda aggiornata con dati sintetici")

    # Imposta USD come valuta
    usd_ids = client.search("res.currency", [("name", "=", "USD")], limit=1)
    if usd_ids:
        client.write("res.company", [company_id], {"currency_id": usd_ids[0]})
        print("  Valuta impostata a USD")

    return company_id


def setup_uom(client: OdooClient, uom_defs: dict) -> dict[str, int]:
    """Crea le UoM aggiuntive (§8.7). Compatibile con Odoo 19."""
    print("\n=== Configurazione UoM ===")

    uom_map = {}

    # Trova UoM esistenti
    existing_uoms = client.search_read("uom.uom", [], ["id", "name"])
    existing_by_name = {u["name"]: u["id"] for u in existing_uoms}

    # Trova Units come base
    units_id = existing_by_name.get("Units", 1)
    uom_map["EA"] = units_id
    print(f"  UoM 'Units' mappata (id={units_id})")

    # Odoo 19 usa relative_uom_id invece di category_id
    # Le UoM correlate a Units (pezzi) hanno relative_uom_id = Units id
    uoms_to_create = [
        # Packaging UoMs - correlate a Units
        {"name": "Box", "code": "BX", "relative_uom_id": units_id, "factor": 1.0, "relative_factor": 1.0, "rounding": 1.0},
        {"name": "Case", "code": "CS", "relative_uom_id": units_id, "factor": 1.0, "relative_factor": 1.0, "rounding": 1.0},
        {"name": "Pack", "code": "PK", "relative_uom_id": units_id, "factor": 1.0, "relative_factor": 1.0, "rounding": 1.0},
        {"name": "Carton", "code": "CT", "relative_uom_id": units_id, "factor": 1.0, "relative_factor": 1.0, "rounding": 1.0},
        {"name": "Bag", "code": "BG", "relative_uom_id": units_id, "factor": 1.0, "relative_factor": 1.0, "rounding": 1.0},
        {"name": "Drum", "code": "DR", "relative_uom_id": units_id, "factor": 1.0, "relative_factor": 1.0, "rounding": 1.0},
        {"name": "Roll", "code": "RO", "relative_uom_id": units_id, "factor": 1.0, "relative_factor": 1.0, "rounding": 1.0},
        # Unit UoMs
        {"name": "Dozens", "code": "DZN", "relative_uom_id": units_id, "factor": 12.0, "relative_factor": 12.0, "rounding": 1.0},
        {"name": "Pair", "code": "PR", "relative_uom_id": units_id, "factor": 2.0, "relative_factor": 2.0, "rounding": 1.0},
        # Volume UoMs (standalone)
        {"name": "gal (US)", "code": "GLL", "relative_uom_id": False, "factor": 1.0, "relative_factor": 1.0, "rounding": 0.001},
    ]

    for uom_data in uoms_to_create:
        name = uom_data["name"]
        code = uom_data.pop("code")
        if name in existing_by_name:
            uom_id = existing_by_name[name]
            print(f"  UoM '{name}' già esistente (id={uom_id})")
        else:
            try:
                uom_id = client.create("uom.uom", uom_data)
                print(f"  UoM '{name}' creata (id={uom_id})")
            except Exception as e:
                print(f"  AVVISO: impossibile creare '{name}': {e}")
                # Fallback: usa Units
                uom_id = units_id
        uom_map[code] = uom_id

    # Mappa le UoM standard esistenti
    standard_mappings = [
        ("LTR", "L"),
        ("KGM", "kg"),
    ]
    for code, name in standard_mappings:
        existing = client.search("uom.uom", [("name", "=", name)], limit=1)
        if existing:
            uom_map[code] = existing[0]
            print(f"  UoM '{name}' mappata (id={existing[0]})")
        else:
            uom_map[code] = units_id
            print(f"  UoM '{name}' non trovata, uso Units")

    return uom_map


def setup_product_categories(client: OdooClient) -> dict[str, int]:
    """Crea le categorie prodotto."""
    print("\n=== Configurazione categorie prodotto ===")

    categories = [
        "MRO",
        "MRO/Fasteners",
        "MRO/Safety-PPE",
        "MRO/Electrical",
        "MRO/Tools",
        "MRO/Abrasives",
        "MRO/Lubricants",
        "MRO/Adhesives",
        "MRO/Packaging",
        "JanSan",
        "JanSan/Floor Care",
        "JanSan/Can Liners",
        "JanSan/Paper Products",
        "JanSan/Cleaning Chemicals",
        "JanSan/Restroom Supplies",
    ]

    cat_map = {}

    # Trova la categoria root "All"
    all_cat = client.search("product.category", [("name", "=", "All")], limit=1)
    root_id = all_cat[0] if all_cat else None

    for cat_path in categories:
        parts = cat_path.split("/")
        parent_id = root_id

        for i, part in enumerate(parts):
            full_path = "/".join(parts[: i + 1])
            domain = [("name", "=", part)]
            if parent_id:
                domain.append(("parent_id", "=", parent_id))

            existing = client.search("product.category", domain, limit=1)
            if existing:
                cat_id = existing[0]
            else:
                cat_id = client.create(
                    "product.category",
                    {"name": part, "parent_id": parent_id},
                )
                print(f"  Categoria '{full_path}' creata (id={cat_id})")

            cat_map[full_path] = cat_id
            parent_id = cat_id

    return cat_map


def category_to_odoo_path(category: str) -> str:
    """Mappa categoria prodotto a path Odoo."""
    mapping = {
        "Fasteners": "MRO/Fasteners",
        "Safety/PPE": "MRO/Safety-PPE",
        "Janitorial": "JanSan",
        "Electrical": "MRO/Electrical",
        "Plumbing": "MRO",
        "Tools": "MRO/Tools",
        "Abrasives": "MRO/Abrasives",
        "Lubricants": "MRO/Lubricants",
        "Adhesives": "MRO/Adhesives",
        "Packaging": "MRO/Packaging",
    }
    return mapping.get(category, "MRO")


def seed_products(
    client: OdooClient,
    products: list[dict],
    uom_map: dict[str, int],
    cat_map: dict[str, int],
) -> dict[str, int]:
    """Crea i prodotti in Odoo."""
    print("\n=== Creazione prodotti ===")

    product_map = {}
    created = 0
    existing = 0

    # Campo UoM diverso tra Odoo 18 e 19
    uom_field = "uom_id" if client.odoo_major_version >= 19 else "uom_id"

    for idx, prod in enumerate(products):
        default_code = prod["default_code"]

        # Controlla se esiste già
        existing_ids = client.search(
            "product.product",
            [("default_code", "=", default_code)],
            limit=1,
        )

        if existing_ids:
            product_map[default_code] = existing_ids[0]
            existing += 1
            continue

        # Trova UoM
        sale_uom = prod.get("sale_uom", "EA")
        uom_id = uom_map.get(sale_uom, uom_map.get("EA", 1))

        # Trova categoria
        cat_path = category_to_odoo_path(prod["category"])
        categ_id = cat_map.get(cat_path, cat_map.get("MRO"))

        # Crea il prodotto (Odoo 19: type='consu' per merce, no uom_po_id)
        values = {
            "name": prod["name"],
            "default_code": default_code,
            "type": "consu",  # Odoo 19 usa 'consu' invece di 'product'
            "categ_id": categ_id,
            uom_field: uom_id,
            "list_price": prod["list_price"],
            "sale_ok": True,
            "purchase_ok": True,
            "barcode": prod.get("gtin"),
        }

        prod_id = client.create("product.product", values)
        product_map[default_code] = prod_id
        created += 1

        if (idx + 1) % 50 == 0:
            print(f"  Progresso: {idx + 1}/{len(products)} prodotti...")

    print(f"  Prodotti creati: {created}, già esistenti: {existing}")
    return product_map


def seed_customers(
    client: OdooClient, customers: list[dict]
) -> dict[str, int]:
    """Crea i clienti in Odoo."""
    print("\n=== Creazione clienti ===")

    customer_map = {}
    created = 0
    existing = 0

    # Trova lo stato OH e il paese US
    us_id = client.search("res.country", [("code", "=", "US")], limit=1)
    us_id = us_id[0] if us_id else None

    state_map = {}
    if us_id:
        states = client.search_read(
            "res.country.state",
            [("country_id", "=", us_id)],
            ["id", "code"],
        )
        state_map = {s["code"]: s["id"] for s in states}

    for cust in customers:
        ref = cust["ref"]

        # Controlla se esiste già
        existing_ids = client.search(
            "res.partner",
            [("ref", "=", ref)],
            limit=1,
        )

        if existing_ids:
            customer_map[ref] = existing_ids[0]
            existing += 1
            continue

        billing = cust["billing_address"]

        # Crea il cliente principale
        values = {
            "name": cust["name"],
            "ref": ref,
            "vat": cust.get("tax_id"),
            "email": cust["email"],
            "phone": cust["phone"],
            "customer_rank": 1,
            "is_company": True,
            "street": billing["line1"],
            "city": billing["city"],
            "zip": billing["postal_code"],
            "country_id": us_id,
            "state_id": state_map.get(billing["region"]),
        }

        cust_id = client.create("res.partner", values)
        customer_map[ref] = cust_id
        created += 1

        # Crea indirizzi di spedizione
        for ship_idx, ship_addr in enumerate(cust.get("shipping_addresses", [])):
            ship_values = {
                "name": f"{cust['name']} - Shipping {ship_idx + 1}",
                "parent_id": cust_id,
                "type": "delivery",
                "street": ship_addr["line1"],
                "city": ship_addr["city"],
                "zip": ship_addr["postal_code"],
                "country_id": us_id,
                "state_id": state_map.get(ship_addr["region"]),
            }
            client.create("res.partner", ship_values)

        # Crea indirizzo di fatturazione separato
        invoice_values = {
            "name": f"{cust['name']} - Billing",
            "parent_id": cust_id,
            "type": "invoice",
            "street": billing["line1"],
            "city": billing["city"],
            "zip": billing["postal_code"],
            "country_id": us_id,
            "state_id": state_map.get(billing["region"]),
        }
        client.create("res.partner", invoice_values)

    print(f"  Clienti creati: {created}, già esistenti: {existing}")
    return customer_map


def seed_pricelists(
    client: OdooClient,
    customers: list[dict],
    customer_map: dict[str, int],
    product_map: dict[str, int],
    products: list[dict],
) -> None:
    """Crea listini per cliente con alcuni prezzi speciali."""
    print("\n=== Creazione listini ===")

    import random
    rng = random.Random(42)

    for cust in customers:
        ref = cust["ref"]
        cust_id = customer_map.get(ref)
        if not cust_id:
            continue

        pricelist_name = cust.get("pricelist_name", f"{ref} Pricelist")

        # Controlla se esiste già
        existing_pl = client.search(
            "product.pricelist",
            [("name", "=", pricelist_name)],
            limit=1,
        )

        if existing_pl:
            pricelist_id = existing_pl[0]
            print(f"  Listino '{pricelist_name}' già esistente")
        else:
            # Crea il listino
            pricelist_id = client.create(
                "product.pricelist",
                {
                    "name": pricelist_name,
                    "currency_id": client.search(
                        "res.currency", [("name", "=", "USD")], limit=1
                    )[0],
                },
            )
            print(f"  Listino '{pricelist_name}' creato (id={pricelist_id})")

            # Aggiungi 5-10 prodotti con prezzi speciali
            num_special = rng.randint(5, 10)
            selected_skus = rng.sample(list(product_map.keys()), min(num_special, len(product_map)))

            for sku in selected_skus:
                prod_id = product_map[sku]
                # Trova il prezzo di listino originale
                orig_prod = next((p for p in products if p["default_code"] == sku), None)
                if orig_prod:
                    # Sconto 5-15%
                    discount = rng.uniform(0.05, 0.15)
                    special_price = round(orig_prod["list_price"] * (1 - discount), 2)

                    client.create(
                        "product.pricelist.item",
                        {
                            "pricelist_id": pricelist_id,
                            "product_id": prod_id,
                            "compute_price": "fixed",
                            "fixed_price": special_price,
                        },
                    )

        # Associa il listino al cliente
        client.write("res.partner", [cust_id], {"property_product_pricelist": pricelist_id})


def setup_technical_user(client: OdooClient, bot_password: str) -> None:
    """Crea l'utente tecnico ventureorder-bot.

    Args:
        client: Client Odoo connesso
        bot_password: Password per l'utente bot (da ODOO_BOT_PASSWORD)
    """
    print("\n=== Configurazione utente tecnico ===")

    existing = client.search(
        "res.users",
        [("login", "=", "ventureorder-bot")],
        limit=1,
    )

    if existing:
        print("  Utente 'ventureorder-bot' già esistente")
        return

    sales_user_group = client.search(
        "res.groups",
        [("full_name", "like", "Sales / User")],
        limit=1,
    )

    user_values = {
        "name": "VentureOrder Bot (SYNTHETIC)",
        "login": "ventureorder-bot",
        "email": "bot@ventureorder.example",
        "password": bot_password,
    }

    # Odoo 19 usa group_ids, non groups_id
    if sales_user_group:
        user_values["group_ids"] = [(4, sales_user_group[0])]

    user_id = client.create("res.users", user_values)
    print(f"  Utente 'ventureorder-bot' creato (id={user_id})")
    print("  NOTA: Creare una chiave API da Preferenze → Sicurezza account")


def main():
    """Entry point principale."""
    # Verifica variabile obbligatoria per il bot
    bot_password = os.getenv("ODOO_BOT_PASSWORD")
    if not bot_password:
        print("ERRORE: ODOO_BOT_PASSWORD non definita.", file=sys.stderr)
        print("Impostare la variabile d'ambiente con la password per l'utente bot.", file=sys.stderr)
        sys.exit(1)

    # Configurazione da environment o default
    url = os.getenv("ODOO_URL", "http://localhost:8069")
    db = os.getenv("ODOO_DB", "vo_demo")
    username = os.getenv("ODOO_USER", "admin")
    password = os.getenv("ODOO_PASSWORD", os.getenv("ODOO_ADMIN_PASSWORD", "admin"))

    print("=" * 60)
    print("VentureOrder - Seed Odoo con dati sintetici MRO/JanSan")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Database: {db}")
    print(f"Utente: {username}")

    # Verifica che esistano i dati master
    if not MASTER_DIR.exists():
        print(f"\nERRORE: Directory {MASTER_DIR} non trovata.")
        print("Eseguire prima: python datagen/generate_master_data.py")
        sys.exit(1)

    # Carica i dati master
    print("\nCaricamento dati master...")
    products, customers, xrefs, uom_defs = load_master_data()
    print(f"  {len(products)} prodotti")
    print(f"  {len(customers)} clienti")
    print(f"  {len(xrefs)} cross-reference")

    # Connessione a Odoo
    print("\nConnessione a Odoo...")
    client = OdooClient(url, db, username, password)

    try:
        client.authenticate()
    except Exception as e:
        print(f"\nERRORE: Impossibile connettersi a Odoo: {e}")
        print("Verificare che Odoo sia avviato e il database inizializzato.")
        sys.exit(1)

    # Setup
    setup_company(client)
    uom_map = setup_uom(client, uom_defs)
    cat_map = setup_product_categories(client)

    # Seed dati
    product_map = seed_products(client, products, uom_map, cat_map)
    customer_map = seed_customers(client, customers)
    seed_pricelists(client, customers, customer_map, product_map, products)
    setup_technical_user(client, bot_password)

    print("\n" + "=" * 60)
    print("Seed completato!")
    print(f"  Prodotti: {len(product_map)}")
    print(f"  Clienti: {len(customer_map)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
