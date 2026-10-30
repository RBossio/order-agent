# Modulo Extract - Estrazione Ordini con LLM Locale

Modulo per l'estrazione di ordini d'acquisto da documenti normalizzati (`NormalizedInput`) al formato `VentureOrder` v1, utilizzando un modello LLM open-source eseguito in locale.

## Caratteristiche

- **Backend LLM locale**: Supporto per Ollama con modelli quantizzati (Qwen2.5-7B-Instruct, Llama 3.1 8B)
- **Pre-elaborazione deterministica**: Estrazione automatica da tabelle Excel/CSV prima dell'LLM
- **Output JSON vincolato**: Prompt con schema JSON e validazione jsonschema
- **Retry automatico**: Se l'output non è valido, riprova con messaggio di errore
- **Punteggi di confidenza**: Per campo e per riga
- **Backend mock**: Per test CI senza GPU

## Installazione

### Prerequisiti

```bash
pip install jsonschema
```

### Installazione Ollama (per uso con LLM reale)

1. **Installa Ollama**:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```

2. **Avvia il server**:
   ```bash
   ollama serve
   ```

3. **Scarica un modello** (scegli uno):
   ```bash
   # Consigliato: Qwen2.5 7B Instruct (4.4GB)
   ollama pull qwen2.5:7b-instruct
   
   # Alternativa: Llama 3.1 8B (4.7GB)
   ollama pull llama3.1:8b
   
   # Per macchine con meno RAM: Qwen2.5 3B
   ollama pull qwen2.5:3b-instruct
   ```

## Uso

### CLI - Singolo file

```bash
# Con backend mock (per test, nessun LLM richiesto)
python -m extract normalized_input.json -o order.json

# Con Ollama
python -m extract normalized_input.json -o order.json --backend ollama

# Con modello specifico
python -m extract normalized_input.json -o order.json --backend ollama --model qwen2.5:7b-instruct

# Output verbose
python -m extract normalized_input.json -o order.json --backend ollama -v
```

### CLI - Batch

```bash
# Processa tutti i file JSON in una cartella
python -m extract cartella_input/ --batch -o cartella_output/

# Con Ollama in batch
python -m extract cartella_input/ --batch -o cartella_output/ --backend ollama
```

### Uso programmatico

```python
from extract import OrderExtractor, OllamaBackend, MockBackend

# Con Ollama
backend = OllamaBackend(model="qwen2.5:7b-instruct")
extractor = OrderExtractor(backend=backend)

# Oppure con mock per test
backend = MockBackend()
extractor = OrderExtractor(backend=backend)

# Estrai da file
result = extractor.extract_from_file("normalized_input.json")

# Oppure da dizionario
result = extractor.extract(normalized_input_dict)

# Accedi ai risultati
print(f"PO Number: {result.order.header.po_number}")
print(f"Righe: {len(result.order.lines)}")
print(f"Confidenza: {result.order.overall_confidence:.0%}")
print(f"Avvisi: {len(result.warnings)}")
```

## Configurazione

### Variabili d'ambiente

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | URL del server Ollama |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Nome del modello |

### Esempio con variabili d'ambiente

```bash
export OLLAMA_HOST="http://192.168.1.100:11434"
export OLLAMA_MODEL="llama3.1:8b"
python -m extract input.json -o output.json --backend ollama
```

## Confidenza e AUTO_POST

La soglia `auto_post_min_score` resta **0,97** come da §7.1 (`config/thresholds.yaml`).
Non è stata abbassata: è la confidenza dell'estrattore a essere tarata sopra quella soglia.

| Fonte | Valore | Perché |
|-------|--------|--------|
| preprocessor solo, controlli ok | 0,98 | un ordine Excel/PDF pulito può AUTO_POST |
| preprocessor e LLM d'accordo | 0,99 | doppia fonte coincidente |
| solo LLM | 0,70 | sotto EXT-01 (0,90) → REVIEW |
| disaccordo o controllo fallito | 0,45 / 0,39 | REVIEW |

`CatalogMatcher.allowlist_synthetic` è **False** di default (UI e produzione: allowlist reale). Solo `make eval` lo attiva, per misurare AUTO_POST come se i clienti sintetici fossero già qualificati (§7.1).

Valuta assente dal documento: se il cliente è in anagrafica si usa `customer.currency` (fonte `catalog`, 0,97); altrimenti USD a 0,50 → REVIEW. Non è DETERMINISTIC 0,98.

Errore silenzioso (eval): ordine in **AUTO_POST** con almeno un campo sbagliato (testata, codice/qty/UoM/prezzo/codice cliente, righe in più o mancanti, valori inventati se la GT è vuota). La percentuale a livello di campo è una metrica separata.

## Valutazione

Comando unico, seed/modello/parametri fissi:

```bash
make eval
# equivalente: python -m extract.eval_run
```

Produce `docs/eval/eval_results.json` (dettaglio ordine per ordine, chiamate/timeout LLM, numeri «prima» sullo stesso campione: 50 ordini, no PDF, no LLM, codice di main pre-PR) e la stessa run con LLM spento (`no_llm`). Nessun PDF in questo campione.

Lo script `eval.py` confronta gli ordini estratti con il ground truth e produce un report Markdown.

### Da documenti sorgente (estrae e valuta)

```bash
# Con mock (veloce, per test struttura)
python -m extract.eval --documents synthetic/documents --ground-truth synthetic/ground_truth

# Con Ollama (valutazione reale)
python -m extract.eval --documents synthetic/documents --ground-truth synthetic/ground_truth --backend ollama

# Campione ridotto
python -m extract.eval --documents synthetic/documents --sample 20 --backend ollama
```

### Da ordini già estratti

```bash
python -m extract.eval --extracted cartella_estratti/ --ground-truth synthetic/ground_truth
```

### Output report

```bash
python -m extract.eval --documents synthetic/documents -o report.md
```

## Architettura

```
extract/
├── __init__.py           # Esporta classi principali
├── __main__.py           # CLI
├── models.py             # Modelli dati (ExtractedOrder, ExtractedLine, etc.)
├── backends/
│   ├── __init__.py
│   ├── base.py           # Interfaccia LLMBackend
│   ├── ollama.py         # Implementazione Ollama HTTP
│   └── mock.py           # Backend deterministico per test
├── preprocessor.py       # Pre-elaborazione tabelle Excel/PDF/email
├── catalog.py            # Matching SKU / xref / UoM / cliente
├── checks.py             # Controlli qty×prezzo, totali, date, anagrafica
├── confidence.py         # Confidenza tarata (non auto-score LLM)
├── dates.py              # Parsing date ISO/US/EU/testuali
├── extractor.py          # Estrattore principale
├── prompts.py            # Prompt e schema JSON
├── eval.py               # Script di valutazione
└── README.md             # Questa documentazione
```

## Pipeline di estrazione

1. **Pre-elaborazione deterministica** (`preprocessor.py`):
   - Excel/PDF: testata (PO, data) da righe chiave-valore e colonne (codice, qty, UoM, prezzo)
   - Email: metadati + liste `1. [SKU]` anche nella signature; quantità in lettere
   - L'LLM **non** viene chiamato se Excel/PDF ha già PO e almeno una riga con quantità

2. **Estrazione LLM** (`extractor.py`):
   - Solo come ripiego (tabella incompleta) e per le email
   - Se preprocessor e LLM discordano: si tiene il valore deterministico, confidenza bassa, REVIEW

3. **Controlli e regole**:
   - qty × prezzo = importo riga; somma righe = totale; articolo/UoM in anagrafica; date plausibili
   - Confidenza calcolata da fonte, accordo tra metodi e controlli (mai dall'auto-score LLM)
   - Controllo fallito → confidenza < 0,90 → EXT-01 e motore regole in REVIEW

## Test

```bash
# Esegui tutti i test
python -m pytest tests/test_extract.py -v

# Solo test velocissimi (mock backend)
python -m pytest tests/test_extract.py -v -k "Mock or Preprocessor"
```

## Note sulle prestazioni

| Backend | Tempo/ordine | Note |
|---------|--------------|------|
| Mock | ~1ms | Solo per test, nessuna estrazione reale |
| Ollama (qwen2.5:7b) | 5-15s | CPU-only, dipende dall'hardware |
| Ollama (qwen2.5:7b) GPU | 1-3s | Con accelerazione CUDA/Metal |

## Limitazioni attuali

- **Matching articoli**: solo SKU esatto e xref (`DatagenReferenceDataProvider`); niente fuzzy/semantico.
- **OCR**: PDF scansionati con `needs_ocr=True` non sono supportati.

## Esempio output

```json
{
  "schema_version": "1.0",
  "order_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "EXTRACTED",
  "header": {
    "po_number": "SW-01050",
    "po_date": "04-23-2026",
    "currency": "USD"
  },
  "buyer": {
    "name": "SafeWork Solutions Inc.",
    "code_on_document": "C-SWS"
  },
  "lines": [
    {
      "line_no": 1,
      "seller_item_code": "PPE-MISC-1108",
      "description": "Safety equipment item 1108",
      "quantity": 6,
      "uom_raw": "EA",
      "unit_price": 15.93
    }
  ],
  "evidence": {
    "/header/po_number": {"confidence": 0.95, "source": "llm"},
    "/lines/0": {"confidence": 0.85, "source": "preprocessor"}
  }
}
```
