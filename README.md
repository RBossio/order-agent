# VentureOrder

**Agente IA per la lettura automatica di ordini d'acquisto B2B**

VentureOrder legge ordini d'acquisto (PDF, Excel, email) ricevuti dai clienti, estrae i dati con LLM locale (Ollama), riconosce clienti e articoli, valida l'ordine e crea bozze `sale.order` in **Odoo 19 Community**.

Piano B: export in CSV, X12 850, EDIFACT ORDERS o Peppol BIS Order.

## Target

Distributori industriali **MRO** (Maintenance, Repair, Operations) e **JanSan** (Janitorial & Sanitation).

## Stato

🚧 **Prototipo** — Solo dati sintetici, nessun dato reale.

## Installazione

```bash
# Crea un virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# oppure: .venv\Scripts\activate  # Windows

# Installa le dipendenze
pip install -e ".[dev]"
```

## Test

```bash
# Esegui tutti i test (esclusi i test di integrazione)
pytest tests/ -v -m "not integration"

# Lint
ruff check .

# Type check
mypy src/ventureorder
```

## Variabili d'ambiente Odoo

Copia `.env.example` in `.env` e imposta i segreti. Make **non** include `.env`
(interpreterebbe `$` e `#` nelle password): `scripts/generate_odoo_conf.py`,
`scripts/seed_odoo.py` e `scripts/smoke_test.py` lo leggono da sé.

I valori con `$` vanno tra **apici singoli** (`POSTGRES_PASSWORD='p$ss#w0rd'`):
Docker Compose interpola `$` se il valore è senza virgolette o tra virgolette
doppie. Il generatore toglie gli apici singoli e tiene il valore letterale, così
`odoo.conf` e Postgres ricevono la stessa password. Le virgolette doppie con `$`
non sono supportate.

| Variabile | Uso |
|-----------|-----|
| `POSTGRES_PASSWORD` | Password PostgreSQL (obbligatoria per `make conf`) |
| `ODOO_ADMIN_PASSWORD` | Master password di Odoo (`admin_passwd` in `odoo.conf`) |
| `ODOO_ADMIN_LOGIN_PASSWORD` | Password di **accesso** dell'utente admin per seed e smoke test. Non è la master password: se manca, gli script escono con codice 1 |
| `ODOO_BOT_PASSWORD` | Password dell'utente tecnico `ventureorder-bot` (obbligatoria per `make seed`; se manca, exit 1) |

## Struttura del repository

```
├── docs/                 # Documentazione (architettura, ADR)
├── schema/               # JSON Schema VOF v1 e esempio
├── samples/              # Esempi di export (CSV, X12, EDIFACT, Peppol)
├── src/ventureorder/     # Codice sorgente
├── config/               # Configurazione YAML (in arrivo)
├── datagen/              # Generatore dati sintetici (in arrivo)
├── eval/                 # Harness per KPI (in arrivo)
├── tests/                # Unit, golden e integration test
└── pyproject.toml        # Configurazione progetto e dipendenze
```

> **Nota**: `docker-compose.yml` e gli script `make` saranno aggiunti nelle prossime PR.

## Documentazione

- [Architettura v0.2](docs/architettura-v0.2.md) — Documento tecnico completo
- [JSON Schema VOF v1](schema/venture-order.v1.schema.json) — Formato d'ordine interno

## Stack tecnologico

| Componente | Tecnologia |
|------------|------------|
| ERP | Odoo 19.0 Community (Docker) |
| LLM | Ollama (locale, es. qwen3:8b) |
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| Database | PostgreSQL 16 |
| EDI/XML | pydifact, lxml, UBL 2.1 |
| OCR | Tesseract 5 (solo scansioni) |

## Vincoli

- ⚠️ **Spesa zero**: nessun account a pagamento, nessuna API cloud
- ⚠️ **Solo dati sintetici**: aziende e persone fittizie, domini `*.example`
- ⚠️ **Solo bozze**: VentureOrder non conferma mai gli ordini
