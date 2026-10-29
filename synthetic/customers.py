"""Generatore clienti deprecato - usare DatagenLoader.

DEPRECATO: Questo modulo è stato sostituito da datagen/master/customers.json.
Usare synthetic.loaders.DatagenLoader per caricare i clienti.

Questo file viene mantenuto solo per compatibilità con EmbeddedLoader
usato nei test quando datagen/master/ non è disponibile.
"""

import warnings
from pathlib import Path
from typing import Any

from . import SEED


def generate_customers(
    catalog: list[dict[str, Any]],
    output_path: Path | None = None
) -> list[dict[str, Any]]:
    """Genera clienti minimi per test di fallback.

    DEPRECATO: Usare DatagenLoader.load_customers() invece.
    Questo metodo genera solo un piccolo set di clienti per test
    quando datagen/master/ non è disponibile.

    Args:
        catalog: Lista articoli del catalogo.
        output_path: Percorso opzionale per salvare il JSON.

    Returns:
        Lista di clienti con anagrafica, stile ordine e cross-reference.
    """
    warnings.warn(
        "generate_customers() è deprecato. Usare DatagenLoader con datagen/master/.",
        DeprecationWarning,
        stacklevel=2
    )

    import json
    import random

    random.seed(SEED + 1)

    customer_refs = [
        "C-TEST01", "C-TEST02", "C-TEST03", "C-TEST04", "C-TEST05",
        "C-TEST06", "C-TEST07", "C-TEST08", "C-TEST09", "C-TEST10"
    ]

    customers: list[dict[str, Any]] = []

    for idx, ref in enumerate(customer_refs):
        uses_codes = idx % 2 == 0
        xref_coverage = 0.7 if uses_codes else 0.0

        xref = []
        if uses_codes and catalog:
            n_items = int(len(catalog) * xref_coverage)
            selected_items = random.sample(catalog, min(n_items, len(catalog)))
            for item in selected_items:
                xref.append({
                    "customer_code": f"{ref.replace('C-', '')[:4]}-{random.randint(1000, 9999)}",
                    "sku": item["sku"],
                    "erp_product_id": item["erp_product_id"],
                    "status": "TRUSTED"
                })

        customers.append({
            "customer_id": ref,
            "name": f"Test Customer {idx + 1} Inc. (SYNTHETIC)",
            "tax_id": f"US{random.randint(10, 99)}-{random.randint(1000000, 9999999)}",
            "erp_partner_id": idx * 3 + 42,
            "erp_partner_ref": ref,
            "email_domain": f"test{idx + 1}.example",
            "contact": {
                "name": f"Test Contact {idx + 1} (fictitious)",
                "email": f"purchasing@test{idx + 1}.example",
                "phone": f"+1-555-{idx:04d}"
            },
            "address": {
                "line1": f"{1000 + idx * 100} Test Street",
                "city": "TestCity",
                "region": "OH",
                "postal_code": f"4{idx:04d}",
                "country": "US"
            },
            "ship_to": [
                {
                    "code": "SHIP-01",
                    "name": f"Test Shipping {idx + 1}",
                    "address": {
                        "line1": f"{1000 + idx * 100} Test Street",
                        "city": "TestCity",
                        "region": "OH",
                        "postal_code": f"4{idx:04d}",
                        "country": "US"
                    }
                }
            ],
            "order_style": {
                "format_preference": ["PDF", "XLSX"] if idx % 3 == 0 else ["EML"] if idx % 3 == 1 else ["XLSX"],
                "po_prefix": f"TEST{idx + 1}-",
                "date_format": "YYYY-MM-DD",
                "uses_own_codes": uses_codes,
                "code_prefix": f"T{idx + 1}-" if uses_codes else None,
                "typical_lines": [2, 6],
                "currency": "USD",
                "language": "en"
            },
            "xref_coverage": xref_coverage,
            "xref": xref
        })

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(customers, f, indent=2, ensure_ascii=False)

    return customers


if __name__ == "__main__":
    from .catalog import generate_catalog

    catalog = generate_catalog()
    customers = generate_customers(catalog, Path(__file__).parent / "data" / "customers.json")
    print(f"Generated {len(customers)} customers (DEPRECATED - use DatagenLoader)")
