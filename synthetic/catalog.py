"""Generatore catalogo deprecato - usare DatagenLoader.

DEPRECATO: Questo modulo è stato sostituito da datagen/master/products.json.
Usare synthetic.loaders.DatagenLoader per caricare il catalogo.

Questo file viene mantenuto solo per compatibilità con EmbeddedLoader
usato nei test quando datagen/master/ non è disponibile.
"""

import warnings
from pathlib import Path
from typing import Any

from . import SEED


def generate_catalog(output_path: Path | None = None) -> list[dict[str, Any]]:
    """Genera un catalogo minimo per test di fallback.

    DEPRECATO: Usare DatagenLoader.load_catalog() invece.
    Questo metodo genera solo un piccolo set di articoli per test
    quando datagen/master/ non è disponibile.

    Args:
        output_path: Percorso opzionale per salvare il JSON.

    Returns:
        Lista di articoli con sku, description, uom, pack, price, erp_product_id.
    """
    warnings.warn(
        "generate_catalog() è deprecato. Usare DatagenLoader con datagen/master/.",
        DeprecationWarning,
        stacklevel=2
    )

    import json
    import random

    random.seed(SEED)

    catalog: list[dict[str, Any]] = []

    categories = [
        ("FASTENERS", "FST", "Fastener"),
        ("PPE", "PPE", "Safety Equipment"),
        ("JANSAN", "JAN", "Cleaning Product"),
        ("LUBRICANTS", "LUB", "Lubricant"),
        ("ABRASIVES", "ABR", "Abrasive"),
        ("TAPES", "TAP", "Tape"),
    ]

    erp_id = 1000
    for idx in range(300):
        cat_name, cat_prefix, cat_desc = categories[idx % len(categories)]
        item_num = idx // len(categories) + 1

        sku = f"{cat_prefix}-TEST-{item_num:03d}"
        pack_count = random.choice([6, 10, 12, 24, 50, 100])

        catalog.append({
            "sku": sku,
            "description": f"{cat_desc} Test Item {item_num} (SYNTHETIC)",
            "uom": "BX" if idx % 2 == 0 else "CS",
            "pack": {
                "raw": f"{pack_count}/BX" if idx % 2 == 0 else f"{pack_count}/CS",
                "inner_count": pack_count,
                "inner_size": 1,
                "inner_uom": "EA"
            },
            "price": round(random.uniform(5.00, 100.00), 2),
            "erp_product_id": erp_id,
            "category": cat_name
        })
        erp_id += 1

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)

    return catalog


if __name__ == "__main__":
    catalog = generate_catalog(Path(__file__).parent / "data" / "catalog.json")
    print(f"Generated {len(catalog)} items (DEPRECATED - use DatagenLoader)")
