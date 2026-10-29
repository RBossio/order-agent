"""Generatore 10 clienti fittizi con stili d'ordine diversi."""

import json
import random
from pathlib import Path
from typing import Any

from . import SEED


def generate_customers(
    catalog: list[dict[str, Any]],
    output_path: Path | None = None
) -> list[dict[str, Any]]:
    """Genera 10 clienti fittizi con stili d'ordine e codici articolo propri.

    Args:
        catalog: Lista articoli del catalogo.
        output_path: Percorso opzionale per salvare il JSON.

    Returns:
        Lista di clienti con anagrafica, stile ordine e cross-reference.
    """
    random.seed(SEED + 1)

    customers: list[dict[str, Any]] = [
        {
            "customer_id": "C001",
            "name": "Acme Manufacturing Inc. (SYNTHETIC)",
            "tax_id": "US12-3456789",
            "erp_partner_id": 42,
            "erp_partner_ref": "C-ACME",
            "email_domain": "acme-mfg.example",
            "contact": {"name": "Jordan Lee (fictitious)", "email": "purchasing@acme-mfg.example", "phone": "+1-555-0100"},
            "address": {"line1": "1200 Industrial Pkwy", "city": "Toledo", "region": "OH", "postal_code": "43601", "country": "US"},
            "ship_to": [
                {"code": "PLANT-01", "name": "Acme Plant 1 - Main", "address": {"line1": "1200 Industrial Pkwy", "city": "Toledo", "region": "OH", "postal_code": "43601", "country": "US"}},
                {"code": "PLANT-02", "name": "Acme Plant 2 - Receiving Dock B", "address": {"line1": "4400 Maumee Ave", "line2": "Dock B", "city": "Toledo", "region": "OH", "postal_code": "43609", "country": "US"}},
            ],
            "order_style": {
                "format_preference": ["PDF", "XLSX"],
                "po_prefix": "45000",
                "date_format": "YYYY-MM-DD",
                "uses_own_codes": True,
                "code_prefix": "ACM-",
                "typical_lines": (3, 8),
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": 0.7
        },
        {
            "customer_id": "C002",
            "name": "Brightway Janitorial Services (SYNTHETIC)",
            "tax_id": "US98-7654321",
            "erp_partner_id": 45,
            "erp_partner_ref": "C-BRIGHT",
            "email_domain": "brightway-jan.example",
            "contact": {"name": "Maria Santos (fictitious)", "email": "orders@brightway-jan.example", "phone": "+1-555-0200"},
            "address": {"line1": "555 Clean Street", "city": "Detroit", "region": "MI", "postal_code": "48201", "country": "US"},
            "ship_to": [
                {"code": "WH-DET", "name": "Detroit Warehouse", "address": {"line1": "555 Clean Street", "city": "Detroit", "region": "MI", "postal_code": "48201", "country": "US"}},
            ],
            "order_style": {
                "format_preference": ["EML", "PDF"],
                "po_prefix": "BW-",
                "date_format": "MM/DD/YYYY",
                "uses_own_codes": False,
                "typical_lines": (5, 15),
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": 0.0
        },
        {
            "customer_id": "C003",
            "name": "Titan Industrial Supply Co. (SYNTHETIC)",
            "tax_id": "US55-1234567",
            "erp_partner_id": 48,
            "erp_partner_ref": "C-TITAN",
            "email_domain": "titan-ind.example",
            "contact": {"name": "Robert Chen (fictitious)", "email": "purchasing@titan-ind.example", "phone": "+1-555-0300"},
            "address": {"line1": "7800 Commerce Blvd", "city": "Cleveland", "region": "OH", "postal_code": "44114", "country": "US"},
            "ship_to": [
                {"code": "MAIN", "name": "Titan Main Facility", "address": {"line1": "7800 Commerce Blvd", "city": "Cleveland", "region": "OH", "postal_code": "44114", "country": "US"}},
                {"code": "EAST", "name": "Titan East Branch", "address": {"line1": "2200 Euclid Ave", "city": "Cleveland", "region": "OH", "postal_code": "44115", "country": "US"}},
            ],
            "order_style": {
                "format_preference": ["XLSX"],
                "po_prefix": "TIT-PO-",
                "date_format": "DD-MMM-YYYY",
                "uses_own_codes": True,
                "code_prefix": "TIS-",
                "typical_lines": (2, 6),
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": 0.8
        },
        {
            "customer_id": "C004",
            "name": "Midwest Building Maintenance (SYNTHETIC)",
            "tax_id": "US44-9876543",
            "erp_partner_id": 51,
            "erp_partner_ref": "C-MBM",
            "email_domain": "mbm-services.example",
            "contact": {"name": "Patricia Johnson (fictitious)", "email": "po@mbm-services.example", "phone": "+1-555-0400"},
            "address": {"line1": "3200 Service Lane", "city": "Columbus", "region": "OH", "postal_code": "43215", "country": "US"},
            "ship_to": [
                {"code": "COL-WH", "name": "Columbus Warehouse", "address": {"line1": "3200 Service Lane", "city": "Columbus", "region": "OH", "postal_code": "43215", "country": "US"}},
            ],
            "order_style": {
                "format_preference": ["EML"],
                "po_prefix": "MBM",
                "date_format": "M/D/YY",
                "uses_own_codes": True,
                "code_prefix": "MB-",
                "typical_lines": (8, 20),
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": 0.5
        },
        {
            "customer_id": "C005",
            "name": "AutoParts Express LLC (SYNTHETIC)",
            "tax_id": "US33-5555555",
            "erp_partner_id": 54,
            "erp_partner_ref": "C-APE",
            "email_domain": "autoparts-exp.example",
            "contact": {"name": "Michael Torres (fictitious)", "email": "buyer@autoparts-exp.example", "phone": "+1-555-0500"},
            "address": {"line1": "9100 Motor Way", "city": "Dearborn", "region": "MI", "postal_code": "48126", "country": "US"},
            "ship_to": [
                {"code": "DB-MAIN", "name": "Dearborn Main", "address": {"line1": "9100 Motor Way", "city": "Dearborn", "region": "MI", "postal_code": "48126", "country": "US"}},
                {"code": "DB-SHOP", "name": "Dearborn Shop", "address": {"line1": "9150 Motor Way", "city": "Dearborn", "region": "MI", "postal_code": "48126", "country": "US"}},
                {"code": "FLINT", "name": "Flint Branch", "address": {"line1": "450 Industrial Dr", "city": "Flint", "region": "MI", "postal_code": "48503", "country": "US"}},
            ],
            "order_style": {
                "format_preference": ["PDF", "EML"],
                "po_prefix": "APE-",
                "date_format": "YYYY/MM/DD",
                "uses_own_codes": True,
                "code_prefix": "AP-",
                "typical_lines": (4, 10),
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": 0.6
        },
        {
            "customer_id": "C006",
            "name": "FreshClean Hospitality Group (SYNTHETIC)",
            "tax_id": "US22-8888888",
            "erp_partner_id": 57,
            "erp_partner_ref": "C-FCH",
            "email_domain": "freshclean-hosp.example",
            "contact": {"name": "Lisa Anderson (fictitious)", "email": "supply@freshclean-hosp.example", "phone": "+1-555-0600"},
            "address": {"line1": "1500 Hospitality Blvd", "city": "Cincinnati", "region": "OH", "postal_code": "45202", "country": "US"},
            "ship_to": [
                {"code": "HOTEL-1", "name": "Downtown Hotel", "address": {"line1": "100 Main St", "city": "Cincinnati", "region": "OH", "postal_code": "45202", "country": "US"}},
                {"code": "HOTEL-2", "name": "Airport Hotel", "address": {"line1": "2800 Terminal Dr", "city": "Hebron", "region": "KY", "postal_code": "41048", "country": "US"}},
            ],
            "order_style": {
                "format_preference": ["PDF"],
                "po_prefix": "FCH-",
                "date_format": "DD/MM/YYYY",
                "uses_own_codes": False,
                "typical_lines": (6, 12),
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": 0.0
        },
        {
            "customer_id": "C007",
            "name": "Northern Manufacturing Corp. (SYNTHETIC)",
            "tax_id": "US77-2222222",
            "erp_partner_id": 60,
            "erp_partner_ref": "C-NMC",
            "email_domain": "northmfg.example",
            "contact": {"name": "David Wilson (fictitious)", "email": "purchasing@northmfg.example", "phone": "+1-555-0700"},
            "address": {"line1": "5500 Factory Rd", "city": "Grand Rapids", "region": "MI", "postal_code": "49503", "country": "US"},
            "ship_to": [
                {"code": "GR-FAC", "name": "Grand Rapids Factory", "address": {"line1": "5500 Factory Rd", "city": "Grand Rapids", "region": "MI", "postal_code": "49503", "country": "US"}},
            ],
            "order_style": {
                "format_preference": ["XLSX", "PDF"],
                "po_prefix": "NMC-",
                "date_format": "YYYY-MM-DD",
                "uses_own_codes": True,
                "code_prefix": "NM-",
                "typical_lines": (3, 7),
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": 0.75
        },
        {
            "customer_id": "C008",
            "name": "SafeWork Solutions Inc. (SYNTHETIC)",
            "tax_id": "US66-3333333",
            "erp_partner_id": 63,
            "erp_partner_ref": "C-SWS",
            "email_domain": "safework-sol.example",
            "contact": {"name": "Jennifer Kim (fictitious)", "email": "orders@safework-sol.example", "phone": "+1-555-0800"},
            "address": {"line1": "800 Safety Lane", "city": "Indianapolis", "region": "IN", "postal_code": "46204", "country": "US"},
            "ship_to": [
                {"code": "IND-WH", "name": "Indianapolis Warehouse", "address": {"line1": "800 Safety Lane", "city": "Indianapolis", "region": "IN", "postal_code": "46204", "country": "US"}},
            ],
            "order_style": {
                "format_preference": ["EML", "XLSX"],
                "po_prefix": "SW-",
                "date_format": "MM-DD-YYYY",
                "uses_own_codes": True,
                "code_prefix": "SWS-",
                "typical_lines": (5, 12),
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": 0.65
        },
        {
            "customer_id": "C009",
            "name": "Premier Tool & Die (SYNTHETIC)",
            "tax_id": "US88-4444444",
            "erp_partner_id": 66,
            "erp_partner_ref": "C-PTD",
            "email_domain": "premier-td.example",
            "contact": {"name": "William Brown (fictitious)", "email": "purchasing@premier-td.example", "phone": "+1-555-0900"},
            "address": {"line1": "1000 Precision Dr", "city": "Fort Wayne", "region": "IN", "postal_code": "46802", "country": "US"},
            "ship_to": [
                {"code": "FW-MAIN", "name": "Fort Wayne Main", "address": {"line1": "1000 Precision Dr", "city": "Fort Wayne", "region": "IN", "postal_code": "46802", "country": "US"}},
                {"code": "FW-TOOL", "name": "Fort Wayne Tool Shop", "address": {"line1": "1050 Precision Dr", "city": "Fort Wayne", "region": "IN", "postal_code": "46802", "country": "US"}},
            ],
            "order_style": {
                "format_preference": ["PDF"],
                "po_prefix": "PTD-",
                "date_format": "DD.MM.YYYY",
                "uses_own_codes": False,
                "typical_lines": (2, 5),
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": 0.0
        },
        {
            "customer_id": "C010",
            "name": "QuickServ Facilities Management (SYNTHETIC)",
            "tax_id": "US99-5555555",
            "erp_partner_id": 69,
            "erp_partner_ref": "C-QSF",
            "email_domain": "quickserv-fm.example",
            "contact": {"name": "Amanda Miller (fictitious)", "email": "orders@quickserv-fm.example", "phone": "+1-555-1000"},
            "address": {"line1": "2400 Facility Way", "city": "Dayton", "region": "OH", "postal_code": "45402", "country": "US"},
            "ship_to": [
                {"code": "DAY-HQ", "name": "Dayton HQ", "address": {"line1": "2400 Facility Way", "city": "Dayton", "region": "OH", "postal_code": "45402", "country": "US"}},
                {"code": "DAY-SUPP", "name": "Dayton Supply Depot", "address": {"line1": "2500 Facility Way", "city": "Dayton", "region": "OH", "postal_code": "45402", "country": "US"}},
            ],
            "order_style": {
                "format_preference": ["EML", "PDF", "XLSX"],
                "po_prefix": "QS-",
                "date_format": "MMM DD, YYYY",
                "uses_own_codes": True,
                "code_prefix": "QSF-",
                "typical_lines": (10, 25),
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": 0.55
        },
    ]

    for customer in customers:
        if customer["order_style"]["uses_own_codes"] and customer.get("xref_coverage", 0) > 0:
            coverage = customer["xref_coverage"]
            prefix = customer["order_style"].get("code_prefix", "")

            n_items = int(len(catalog) * coverage)
            selected_items = random.sample(catalog, n_items)

            xref = []
            for item in selected_items:
                cat_abbr = {
                    "FASTENERS": "HW",
                    "PPE": "PPE",
                    "JANSAN_LINERS": "JS",
                    "JANSAN_CHEMICALS": "JS",
                    "JANSAN_PAPER": "JS",
                    "ABRASIVES": "ABR",
                    "TAPES": "TAP",
                    "LUBRICANTS": "LUB",
                    "MISC": "MIS"
                }.get(item.get("category", "MISC"), "MIS")

                customer_code = f"{prefix}{cat_abbr}-{random.randint(1000, 9999):04d}"
                xref.append({
                    "customer_code": customer_code,
                    "sku": item["sku"],
                    "erp_product_id": item["erp_product_id"],
                    "status": "TRUSTED"
                })

            customer["xref"] = xref
        else:
            customer["xref"] = []

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(customers, f, indent=2, ensure_ascii=False)

    return customers


if __name__ == "__main__":
    from .catalog import generate_catalog

    catalog = generate_catalog()
    customers = generate_customers(catalog, Path(__file__).parent / "data" / "customers.json")
    print(f"Generated {len(customers)} customers")
    for c in customers:
        print(f"  - {c['name']}: {len(c.get('xref', []))} xref entries")
