# VentureOrder - Generatore Dati Sintetici

Generatore di dati sintetici per il prototipo VentureOrder. Produce un dataset completo di ordini MRO/JanSan per testare l'agente di estrazione ordini.

## Contenuto del Dataset

| Componente | Quantità | Descrizione |
|------------|----------|-------------|
| **Catalogo** | 300 articoli | Articoli MRO/JanSan realistici con SKU, descrizione, UoM, confezioni e prezzi |
| **Clienti** | 10 | Clienti fittizi con stili d'ordine diversi e cross-reference codici |
| **Ordini** | 150 | Distribuiti tra PDF (~50), Excel (~50) e email EML (~50) |
| **Casi difficili** | ~22 (15%) | Ordini con complessità aggiuntive per testare robustezza |

### Categorie Articoli

- **FASTENERS** (60): Viti, bulloni, dadi, rondelle
- **PPE** (50): Guanti, occhiali, maschere, DPI
- **JANSAN_LINERS** (40): Sacchi spazzatura
- **JANSAN_CHEMICALS** (26): Detergenti, disinfettanti
- **JANSAN_PAPER** (20): Carta asciugamani, carta igienica
- **ABRASIVES** (32): Carte vetrate, dischi abrasivi
- **TAPES** (15): Nastri adesivi
- **LUBRICANTS** (18): Oli, grassi, lubrificanti
- **MISC** (39): Utensili, batterie, contenitori

### Tipi di Casi Difficili

| Tipo | Descrizione | Riferimento |
|------|-------------|-------------|
| `UOM_CONVERSION` | Confezioni con conversione UoM (4/1 GAL, 100/BX) | §6.4 arch. |
| `UOM_CARTON` | Conversione da cartone (CS → BX/EA/RL) allineata a products.json | §7.2 UOM-03 |
| `CUSTOMER_CODES` | Codici articolo del cliente invece che interni | §6.2 arch. |
| `UNKNOWN_CUSTOMER_CODE` | Codice articolo cliente assente in xref (ITM-01) | §7.2 ITM |
| `AMBIGUOUS_CUSTOMER_CODE` | Codice cliente in conflitto con GTIN/MPN (ITM-04) | §7.2 ITM |
| `PRICE_OUT_OF_TOLERANCE` | Prezzo PO oltre ±2% rispetto al listino (PRC-01) | §7.2 PRC |
| `DUP_PO` | Stesso PO già POSTED per il cliente (DUP-01) | §7.2 DUP |
| `AMBIGUOUS_DESC` | Descrizioni ambigue senza attributi chiave | §6.3 arch. |
| `TYPO_DESC` | Descrizioni con refusi | §6.3 arch. |
| `TOTAL_MIXED` | Righe di totale/note mescolate con articoli | - |
| `MULTIPAGE_PDF` | PDF con più pagine | - |
| `DATE_FORMAT` | Date in formati diversi (US, EU, testo) | - |
| `QTY_WORDS` | Quantità scritte a parole | - |
| `EMAIL_CONTRADICTORY` | Email con testo e allegato contraddittori | - |
| `MISSING_PO_NUMBER` | Numero PO mancante (deve fallire HDR-01) | §7.2 arch. |
| `MISSING_QTY` | Quantità mancante (deve fallire QTY-01) | §7.2 arch. |
| `MISSING_DATE` | Data ordine mancante (review HDR-02) | §7.2 arch. |

## Struttura Directory

```
synthetic/
├── __init__.py           # Seed fisso (42)
├── generator.py          # Script principale
├── catalog.py            # Generatore catalogo (embedded)
├── customers.py          # Generatore clienti (embedded)
├── orders.py             # Generatore ordini e documenti
├── loaders/              # Interfaccia per dati master
│   ├── __init__.py       # MasterDataLoader protocol e get_loader()
│   ├── embedded.py       # Loader che usa catalog.py/customers.py
│   └── datagen.py        # Loader per datagen/master/ (futuro)
├── data/
│   ├── catalog.json      # 300 articoli
│   ├── customers.json    # 10 clienti con xref
│   ├── manifest.json     # Manifest completo
│   └── manifest.csv      # Manifest in formato CSV
├── documents/
│   ├── pdf/              # Ordini in formato PDF
│   ├── xlsx/             # Ordini in formato Excel
│   └── eml/              # Ordini in formato email
└── ground_truth/         # Ground truth JSON per ogni ordine
```

## Architettura Dati Master

Il generatore usa un'interfaccia `MasterDataLoader` per caricare catalogo, clienti e cross-reference. Questo permette di sostituire la fonte dei dati senza modificare il generatore degli ordini.

### Fonti Disponibili

| Loader | Fonte | Stato |
|--------|-------|-------|
| `EmbeddedLoader` | `catalog.py`, `customers.py` | ✅ Attivo (fallback) |
| `DatagenLoader` | `datagen/master/` | 🔜 Quando disponibile |

### Priorità di Caricamento

1. Se `datagen/master/` esiste → usa `DatagenLoader`
2. Altrimenti → usa `EmbeddedLoader`

Per forzare l'uso dei dati embedded:
```bash
python3 -m synthetic.generator --use-embedded
```

### Integrazione con datagen/master/

Quando l'altra PR introdurrà i dati deterministici in `datagen/master/`, il generatore li userà automaticamente. Formato atteso:

```
datagen/master/
├── catalog.json           # 300 articoli con stesso schema
├── customers.json         # 10 clienti
└── customer_item_xref.json # Tabella codici cliente (opzionale)
```

Vedere `datagen/README.md` per il formato completo.

## Come Rigenerare

### Prerequisiti

```bash
pip install -r requirements.txt
```

### Generazione Completa

```bash
python3 -m synthetic.generator
```

### Opzioni

```bash
python3 -m synthetic.generator --help

# Parametri disponibili:
#   --output-dir DIR        Directory di output (default: synthetic/)
#   --num-orders N          Numero di ordini (default: 150)
#   --hard-case-pct PCT     Percentuale casi difficili (default: 0.15)
#   -v, --verbose           Output dettagliato
```

### Riproducibilità

Il generatore usa un **seed fisso** (`SEED = 42` in `__init__.py`) per garantire risultati riproducibili. Ogni esecuzione con gli stessi parametri produce esattamente gli stessi dati.

## Validazione

### Esecuzione Test

```bash
python3 -m pytest tests/ -v
```

### Test Inclusi

| Test | Verifica |
|------|----------|
| `test_catalog_size` | Catalogo ha esattamente 300 articoli |
| `test_catalog_unique_skus` | SKU univoci |
| `test_customers_count` | 10 clienti |
| `test_customers_with_xref` | Almeno 5 clienti hanno codici propri |
| `test_ground_truth_schema_validation` | Tutti i ground truth validi contro lo schema VOF v1 |
| `test_hard_cases_count` | ~15% casi difficili |
| `test_hard_case_types_variety` | Almeno 8 tipi diversi di casi difficili |
| `test_validation_issues_for_blocking_cases` | Casi con campi mancanti hanno issue BLOCK |

## Schema Ground Truth

I file ground truth in `ground_truth/` sono conformi allo schema `schema/venture-order.v1.schema.json` (VOF v1).

Campi principali:
- `order_id`: UUID univoco
- `tenant_id`: Sempre "delta-industrial-supply"
- `document_type`: Sempre "ORIGINAL"
- `status`: "VALIDATED" o "NEEDS_REVIEW"
- `source`: Canale, documenti con hash SHA256
- `buyer`, `ship_to`: Anagrafica cliente
- `header`: PO number, date, currency
- `lines`: Righe con codici, descrizioni, quantità, UoM, prezzi
- `validation.issues`: Problemi rilevati (se presenti)
- `_synthetic_metadata`: Metadati per test (is_hard_case, hard_case_types)

## Uso nei Test dell'Agente

```python
import json
from pathlib import Path

# Carica manifest
with open("synthetic/data/manifest.json") as f:
    manifest = json.load(f)

# Itera sugli ordini
for order_entry in manifest["orders"]:
    # Leggi documento sorgente
    doc_path = Path("synthetic") / order_entry["document_path"]
    
    # Leggi ground truth atteso
    gt_path = Path("synthetic") / order_entry["ground_truth_path"]
    with open(gt_path) as f:
        expected = json.load(f)
    
    # Estrai con l'agente (da implementare)
    # extracted = agent.extract(doc_path)
    
    # Confronta
    # assert extracted["header"]["po_number"] == expected["header"]["po_number"]
```

## Licenza

Dataset sintetico per uso interno nel prototipo VentureOrder. Tutti i nomi di aziende, persone, indirizzi e codici fiscali sono fittizi e contrassegnati con "(SYNTHETIC)" o "(fictitious)".
