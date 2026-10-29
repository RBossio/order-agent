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

## Valutazione

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
├── preprocessor.py       # Pre-elaborazione tabelle strutturate
├── extractor.py          # Estrattore principale
├── prompts.py            # Prompt e schema JSON
├── eval.py               # Script di valutazione
└── README.md             # Questa documentazione
```

## Pipeline di estrazione

1. **Pre-elaborazione** (`preprocessor.py`):
   - Estrae metadati email (PO number, mittente)
   - Mappa colonne tabelle Excel/CSV
   - Estrae righe strutturate senza LLM
   - Identifica righe ambigue che richiedono LLM

2. **Estrazione LLM** (`extractor.py`):
   - Costruisce prompt con contesto pre-elaborato
   - Chiama il backend LLM
   - Parsa risposta JSON
   - Retry se validazione fallisce

3. **Validazione**:
   - Validazione output contro `venture-order.v1.schema.json`
   - Genera avvisi per campi mancanti o non validi

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

- **Risoluzione codici**: I codici articolo (seller_item_code, buyer_item_code) NON vengono risolti verso il catalogo. Questa funzionalità sarà implementata nella fase successiva.
- **Matching clienti**: I clienti NON vengono matchati con l'anagrafica ERP.
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
