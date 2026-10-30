#!/usr/bin/env python3
"""
Test di smoke per verificare il setup Odoo.

Verifica:
1. Connessione a Odoo via XML-RPC
2. 300 prodotti presenti
3. 10 clienti presenti
4. Crea e cancella un sale.order in bozza

Esito: 0 = successo, 1 = fallimento
"""

import os
import sys
import xmlrpc.client
from pathlib import Path


def _load_project_dotenv() -> None:
    """Carica `.env` del repo senza passare da Make (`$` e `#` restano intatti)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from generate_odoo_conf import load_dotenv

    load_dotenv(env_path)


def main():
    _load_project_dotenv()

    url = os.getenv("ODOO_URL", "http://localhost:8069")
    db = os.getenv("ODOO_DB", "vo_demo")
    username = os.getenv("ODOO_USER", "admin")
    password = os.getenv("ODOO_ADMIN_LOGIN_PASSWORD")
    if not password:
        print("ERRORE: ODOO_ADMIN_LOGIN_PASSWORD non definita.", file=sys.stderr)
        print(
            "Impostare la password di accesso dell'utente admin "
            "(non usare la master password ODOO_ADMIN_PASSWORD).",
            file=sys.stderr,
        )
        sys.exit(1)

    print("=" * 60)
    print("VentureOrder - Smoke Test Odoo")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Database: {db}")

    errors = []

    # Test 1: Connessione
    print("\n[1/4] Test connessione XML-RPC...")
    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        version = common.version()
        print(f"      OK - Odoo {version.get('server_version', 'unknown')}")
    except Exception as e:
        errors.append(f"Connessione fallita: {e}")
        print(f"      FAIL - {e}")
        print("\n" + "=" * 60)
        print("SMOKE TEST FALLITO")
        print("=" * 60)
        sys.exit(1)

    # Autenticazione
    try:
        uid = common.authenticate(db, username, password, {})
        if not uid:
            raise RuntimeError("Autenticazione fallita")
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    except Exception as e:
        errors.append(f"Autenticazione fallita: {e}")
        print(f"      FAIL - Autenticazione: {e}")
        print("\n" + "=" * 60)
        print("SMOKE TEST FALLITO")
        print("=" * 60)
        sys.exit(1)

    def execute(model, method, *args, **kwargs):
        return models.execute_kw(db, uid, password, model, method, args, kwargs)

    # Test 2: Verifica prodotti
    print("\n[2/4] Verifica prodotti (attesi >= 300)...")
    try:
        product_count = execute("product.product", "search_count", [("sale_ok", "=", True)])
        if product_count >= 300:
            print(f"      OK - {product_count} prodotti trovati")
        else:
            errors.append(f"Prodotti insufficienti: {product_count} (attesi >= 300)")
            print(f"      FAIL - Solo {product_count} prodotti (attesi >= 300)")
    except Exception as e:
        errors.append(f"Errore conteggio prodotti: {e}")
        print(f"      FAIL - {e}")

    # Test 3: Verifica clienti
    print("\n[3/4] Verifica clienti (attesi >= 10)...")
    try:
        customer_count = execute(
            "res.partner",
            "search_count",
            [("customer_rank", ">", 0), ("is_company", "=", True)],
        )
        if customer_count >= 10:
            print(f"      OK - {customer_count} clienti trovati")
        else:
            errors.append(f"Clienti insufficienti: {customer_count} (attesi >= 10)")
            print(f"      FAIL - Solo {customer_count} clienti (attesi >= 10)")
    except Exception as e:
        errors.append(f"Errore conteggio clienti: {e}")
        print(f"      FAIL - {e}")

    # Test 4: Crea e cancella sale.order
    print("\n[4/4] Test creazione/cancellazione sale.order in bozza...")
    order_id = None
    try:
        # Trova un cliente e un prodotto
        customers = execute(
            "res.partner",
            "search_read",
            [("customer_rank", ">", 0), ("is_company", "=", True)],
            fields=["id"],
            limit=1,
        )
        products = execute(
            "product.product",
            "search_read",
            [("sale_ok", "=", True)],
            fields=["id"],
            limit=1,
        )

        if not customers or not products:
            raise RuntimeError("Nessun cliente o prodotto trovato")

        partner_id = customers[0]["id"]
        product_id = products[0]["id"]

        # Crea ordine di test
        order_values = {
            "partner_id": partner_id,
            "client_order_ref": "VO-SMOKE-TEST",
            "origin": "VO:smoke-test-00000000-0000-0000-0000-000000000000",
            "order_line": [
                [
                    0,
                    0,
                    {
                        "product_id": product_id,
                        "product_uom_qty": 1,
                    },
                ]
            ],
        }

        order_id = execute("sale.order", "create", order_values)
        print(f"      Ordine creato: id={order_id}")

        # Verifica stato draft
        order = execute(
            "sale.order",
            "search_read",
            [("id", "=", order_id)],
            fields=["state", "name"],
        )
        if order and order[0]["state"] == "draft":
            print(f"      Ordine in stato draft: {order[0]['name']}")
        else:
            raise RuntimeError(f"Stato ordine non draft: {order}")

        # Cancella l'ordine
        execute("sale.order", "unlink", [order_id])
        print("      Ordine cancellato")
        print("      OK - Ciclo create/delete completato")

    except Exception as e:
        errors.append(f"Errore test sale.order: {e}")
        print(f"      FAIL - {e}")
        # Tenta cleanup
        if order_id:
            try:
                execute("sale.order", "unlink", [order_id])
            except Exception:
                pass

    # Risultato finale
    print("\n" + "=" * 60)
    if errors:
        print("SMOKE TEST FALLITO")
        print("=" * 60)
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("SMOKE TEST COMPLETATO CON SUCCESSO")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
