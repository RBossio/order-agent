# Modulo Ingest - VentureOrder

Modulo Python per l'ingestione di documenti d'ordine (email, PDF, Excel, CSV) e la produzione di un input normalizzato per la fase successiva di estrazione IA.

## Indice

- [Installazione](#installazione)
- [Uso](#uso)
  - [Come libreria Python](#come-libreria-python)
  - [Da linea di comando (CLI)](#da-linea-di-comando-cli)
- [Formati supportati](#formati-supportati)
- [Schema NormalizedInput](#schema-normalizedinput)
- [Test](#test)

## Installazione

```bash
pip install -r requirements.txt
```

Dipendenze principali:
- `pdfplumber>=0.10.0` - Estrazione testo e tabelle da PDF
- `openpyxl>=3.1.0` - Parsing file Excel .xlsx
- `xlrd>=2.0.0` - Parsing file Excel .xls legacy
- `jsonschema>=4.20.0` - Validazione output

## Uso

### Come libreria Python

```python
from ingest import Ingestor

# Crea l'ingestor
ingestor = Ingestor()

# Ingestisce un singolo file
result = ingestor.ingest("ordine.pdf")

# Accedi ai dati normalizzati
print(f"File: {result.source.filename}")
print(f"Parti estratte: {len(result.parts)}")

for part in result.parts:
    print(f"  - {part.part_type.value}: {len(part.text or '')} caratteri")
    if part.tables:
        print(f"    Tabelle: {len(part.tables)}")

# Salva come JSON
Ingestor.save_json(result, "output.json")

# Oppure ottieni la stringa JSON
json_str = Ingestor.to_json(result)
```

#### Elaborazione batch

```python
from ingest import Ingestor

ingestor = Ingestor()

# Processa tutti i file in una cartella
results = ingestor.ingest_batch(
    "ordini/",
    recursive=True,  # Cerca anche nelle sottocartelle
    extensions=[".pdf", ".xlsx"]  # Solo questi formati
)

for file_path, result, error in results:
    if error:
        print(f"ERRORE: {file_path} - {error}")
    else:
        print(f"OK: {file_path} - {len(result.parts)} parti")
```

### Da linea di comando (CLI)

```bash
# Ingestisce un singolo file
python -m ingest ordine.pdf -o output.json

# Ingestisce con output su stdout
python -m ingest ordine.pdf

# Modalità batch su una cartella
python -m ingest cartella_ordini/ --batch -o output_dir/

# Batch ricorsivo
python -m ingest cartella_ordini/ --batch -r -o output_dir/

# Filtra per estensione
python -m ingest cartella_ordini/ --batch -e .pdf,.xlsx -o output_dir/

# Valida l'output contro lo schema
python -m ingest ordine.pdf -o output.json --validate

# Output compatto (senza indentazione)
python -m ingest ordine.pdf -o output.json --indent 0
```

## Formati supportati

### Email (.eml)

Il parser email estrae:
- **Metadati**: mittente, destinatari (To, CC), oggetto, data, Message-ID
- **Corpo**: preferisce text/plain, altrimenti estrae testo pulito da HTML
- **Firma**: separata dal corpo principale (rilevamento euristico)
- **Citazioni**: testo citato separato (es. risposte a email precedenti)
- **Allegati**: processati automaticamente se di tipo supportato (PDF, Excel, CSV)

### PDF

Il parser PDF (basato su pdfplumber) estrae:
- **Testo per pagina**: sia semplice che con layout preservato
- **Tabelle**: rilevamento automatico con strategie multiple
- **Flag `needs_ocr`**: segnala PDF scansionati senza testo estraibile

> ⚠️ I PDF scansionati sono rilevati ma NON viene eseguito OCR in questa fase.

### Excel (.xlsx, .xls)

Il parser Excel estrae:
- **Tutti i fogli**: ogni foglio diventa una parte separata
- **Griglia completa**: tutte le celle con valori
- **Riferimenti cella**: es. A1, B2
- **Celle unite**: rilevate e segnalate
- **Riga intestazione**: rilevamento euristico basato su keyword

### CSV

Il parser CSV:
- **Rileva automaticamente**: encoding (UTF-8, Latin-1, etc.) e delimitatore (, ; \t |)
- **Converte tipi**: numeri interi e decimali dove possibile
- **Identifica intestazione**: basato su keyword comuni

## Schema NormalizedInput

L'output segue lo schema JSON definito in `schema/normalized-input.v1.schema.json`.

### Struttura principale

```json
{
  "schema_version": "1.0",
  "input_id": "uuid",
  "source": {
    "filename": "ordine.pdf",
    "sha256": "...",
    "file_type": "PDF",
    "file_size_bytes": 12345
  },
  "email_metadata": { /* solo per .eml */ },
  "ingested_at": "2024-01-15T10:30:00Z",
  "parts": [
    {
      "part_id": "part-abc123",
      "part_type": "PDF_PAGE",
      "sha256": "...",
      "text": "contenuto testuale",
      "text_layout": "testo con layout preservato",
      "tables": [ /* tabelle rilevate */ ],
      "page_number": 1,
      "needs_ocr": false
    }
  ],
  "warnings": [
    {
      "code": "PDF-01",
      "message": "PDF sembra essere una scansione"
    }
  ]
}
```

### Tipi di parte (`part_type`)

| Tipo | Descrizione |
|------|-------------|
| `EMAIL_BODY` | Corpo email (text/plain) |
| `EMAIL_BODY_HTML` | Corpo email estratto da HTML |
| `EMAIL_SIGNATURE` | Firma email |
| `EMAIL_QUOTED` | Testo citato/reply |
| `PDF_PAGE` | Pagina PDF |
| `EXCEL_SHEET` | Foglio Excel |
| `CSV_DATA` | Dati CSV |
| `ATTACHMENT` | Allegato non processato |

### Codici di avviso

| Codice | Significato |
|--------|-------------|
| `PDF-01` | PDF scansionato, richiede OCR |
| `PDF-02` | Errore nel parsing PDF |
| `PDF-03` | Errore estrazione tabelle |
| `XLS-01` | Errore parsing Excel |
| `XLS-02` | Libreria xlrd mancante |
| `CSV-01` | Errore parsing CSV |
| `ATT-01` | Tipo allegato non supportato |
| `ATT-02` | Errore parsing allegato |

## Test

Esegui i test con pytest:

```bash
# Tutti i test
pytest tests/test_ingest.py -v

# Solo test veloci
pytest tests/test_ingest.py -v -k "not TestAllSyntheticDocuments"

# Test su tutti i 150 documenti sintetici
pytest tests/test_ingest.py -v -k "TestAllSyntheticDocuments"

# Test con copertura
pytest tests/test_ingest.py -v --cov=ingest --cov-report=term-missing
```

I test verificano:
- Ingestione senza errori di tutti i 150 ordini sintetici
- Validazione dell'output contro lo schema JSON
- Estrazione di parti, testo e tabelle
- Coerenza con il ground truth (numero righe, etc.)
- Gestione di casi limite ed errori

## Struttura del modulo

```
ingest/
├── __init__.py         # Export pubblici
├── __main__.py         # CLI
├── models.py           # Modelli dati (NormalizedInput, Part, Table, etc.)
├── ingestor.py         # Classe Ingestor principale
├── parsers/
│   ├── __init__.py
│   ├── eml_parser.py   # Parser email
│   ├── pdf_parser.py   # Parser PDF
│   ├── excel_parser.py # Parser Excel
│   └── csv_parser.py   # Parser CSV
└── README.md           # Questo file
```

## Limitazioni note

1. **OCR non implementato**: i PDF scansionati sono rilevati ma non processati
2. **Allegati immagine**: segnalati ma non estratti (es. .jpg, .png in email)
3. **Password PDF/Excel**: file protetti non supportati
4. **Macro Excel**: ignorate, solo dati estratti

## Sviluppi futuri

- [ ] Integrazione OCR (Tesseract) per PDF scansionati
- [ ] Supporto file .doc/.docx
- [ ] Estrazione immagini da PDF
- [ ] Riconoscimento layout documenti strutturati
