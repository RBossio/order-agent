# Test di integrazione

Test che richiedono Odoo, Ollama e altri servizi esterni.
Eseguiti solo in locale, non in CI.

```bash
# Tutti i test di integrazione (Odoo deve essere su e seedato)
pytest tests/integration/ -m integration

# Solo connettore Odoo
pytest tests/integration/test_odoo_live.py -m integration -v
```

Il test `test_post_draft_against_real_odoo` si salta da solo se Odoo
non risponde su `ODOO_URL` o se mancano le credenziali
(`ODOO_PASSWORD` / `ODOO_ADMIN_PASSWORD`). Serve il seed MRO
(`make seed`: cliente `C-ACME`, SKU `ADH-EPX-000`).
