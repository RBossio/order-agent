#!/usr/bin/env python3
"""
VentureOrder - Generatore dati sintetici

Genera un dataset completo di ordini MRO/JanSan sintetici per il prototipo VentureOrder.

Uso:
    python -m synthetic.generator [--output-dir DIR] [--num-orders N] [--hard-case-pct PCT]
    
Esempio:
    python -m synthetic.generator --output-dir ./synthetic --num-orders 150 --hard-case-pct 0.15
"""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Genera dati sintetici per VentureOrder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Directory di output (default: synthetic/)"
    )
    parser.add_argument(
        "--num-orders",
        type=int,
        default=150,
        help="Numero di ordini da generare (default: 150)"
    )
    parser.add_argument(
        "--hard-case-pct",
        type=float,
        default=0.15,
        help="Percentuale di casi difficili (default: 0.15)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Output dettagliato"
    )
    parser.add_argument(
        "--use-embedded",
        action="store_true",
        help="Usa sempre i dati embedded, anche se datagen/master/ esiste"
    )
    
    args = parser.parse_args()
    
    from .loaders import get_loader
    from .orders import generate_orders
    
    print(f"VentureOrder - Generatore dati sintetici")
    print(f"========================================")
    print(f"Output directory: {args.output_dir}")
    print(f"Numero ordini: {args.num_orders}")
    print(f"Percentuale casi difficili: {args.hard_case_pct * 100:.0f}%")
    print()
    
    loader = get_loader(prefer_datagen=not args.use_embedded)
    loader_name = type(loader).__name__
    print(f"Fonte dati master: {loader_name}")
    print()
    
    print("1. Caricamento catalogo articoli...")
    catalog = loader.load_catalog(args.output_dir / "data" / "catalog.json")
    print(f"   ✓ {len(catalog)} articoli caricati")
    
    categories = {}
    for item in catalog:
        cat = item.get("category", "UNKNOWN")
        categories[cat] = categories.get(cat, 0) + 1
    
    if args.verbose:
        print("   Distribuzione per categoria:")
        for cat, count in sorted(categories.items()):
            print(f"     - {cat}: {count}")
    print()
    
    print("2. Caricamento clienti...")
    customers = loader.load_customers(catalog, args.output_dir / "data" / "customers.json")
    print(f"   ✓ {len(customers)} clienti caricati")
    
    if args.verbose:
        print("   Clienti:")
        for c in customers:
            xref_count = len(c.get("xref", []))
            print(f"     - {c['customer_id']}: {c['name'][:40]}... ({xref_count} xref)")
    print()
    
    print("3. Generazione ordini...")
    ground_truths, manifest = generate_orders(
        catalog, 
        customers, 
        args.output_dir,
        num_orders=args.num_orders,
        hard_case_pct=args.hard_case_pct
    )
    print(f"   ✓ {len(ground_truths)} ordini generati")
    print(f"   ✓ {manifest['hard_cases']} casi difficili ({manifest['hard_case_percentage']}%)")
    print(f"   ✓ Distribuzione formati: {manifest['format_distribution']}")
    print()
    
    print("4. Riepilogo file generati:")
    print(f"   - {args.output_dir / 'data' / 'catalog.json'}")
    print(f"   - {args.output_dir / 'data' / 'customers.json'}")
    print(f"   - {args.output_dir / 'data' / 'manifest.json'}")
    print(f"   - {args.output_dir / 'data' / 'manifest.csv'}")
    print(f"   - {args.output_dir / 'documents' / 'pdf' / '*.pdf'} ({manifest['format_distribution']['PDF']} file)")
    print(f"   - {args.output_dir / 'documents' / 'xlsx' / '*.xlsx'} ({manifest['format_distribution']['XLSX']} file)")
    print(f"   - {args.output_dir / 'documents' / 'eml' / '*.eml'} ({manifest['format_distribution']['EML']} file)")
    print(f"   - {args.output_dir / 'ground_truth' / '*.json'} ({len(ground_truths)} file)")
    print()
    
    print("Generazione completata con successo!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
