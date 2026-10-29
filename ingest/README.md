# Modulo Ingest - VentureOrder

Modulo Python per l'ingestione di documenti d'ordine (email, PDF, Excel, CSV) e la produzione di un input normalizzato per la fase successiva di estrazione IA.

## Indice

- [Installazione](#installazione)
- [Uso](#uso)
  - [Come libreria Python](#come-libreria-python)
  - [Da linea di comando (CLI)](#da-linea-di-comando-cli)
- [Sicurezza](#sicurezza)
  - [Limiti di dimensione](#limiti-di-dimensione)
  - [Rilevamento tipo file](#rilevamento-tipo-file)
  - [Protezione zip bomb](#protezione-zip-bomb)
  - [Sanificazione nomi file](#sanificazione-nomi-file)
  - [Configurazione personalizzata](#configurazione-personalizzata)
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

## Sicurezza

Il modulo include robuste funzionalità di sicurezza per gestire file potenzialmente malevoli.

### Limiti di dimensione

Limiti configurabili per prevenire attacchi DoS:

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `max_file_size_bytes` | 25 MB | Dimensione massima per singolo file |
| `max_email_total_size_bytes` | 50 MB | Dimensione massima totale email (inclusi allegati) |
| `max_attachments` | 20 | Numero massimo di allegati per email |
| `max_xlsx_decompressed_size_bytes` | 100 MB | Dimensione massima decompressa per file XLSX |

Quando un limite viene superato, il file viene rifiutato con un errore chiaro nel campo `warnings` del `NormalizedInput` (severity: `ERROR`).

### Rilevamento tipo file

Il tipo reale del file viene rilevato dai **magic number** (primi byte), NON dall'estensione:

| Tipo | Magic Number | Descrizione |
|------|--------------|-------------|
| PDF | `%PDF` | File PDF |
| XLSX | `PK` + `[Content_Types].xml` | Excel OOXML |
| XLS | `D0 CF 11 E0...` | Excel OLE2 legacy |
| XLSM | `PK` + vbaProject marker | Excel con macro |
| EML | Header email (From:, To:, etc.) | Email |
| CSV | Testo con delimitatori | Dati tabulari |
| PE | `MZ` + `PE\x00\x00` | Eseguibile Windows |
| ELF | `\x7fELF` | Eseguibile Linux |
| Mach-O | `\xFE\xED\xFA\xCE/CF` | Eseguibile macOS |
| Script | `#!/...` | Script con shebang |

**Comportamenti:**
- Se l'estensione non corrisponde al tipo rilevato → **warning** (es. `.pdf` ma contenuto è `.exe`)
- Tipi eseguibili → **rifiutato** con errore
- File con macro (`.xlsm`) → **rifiutato** con errore (configurabile)

### Protezione zip bomb

I file XLSX (che sono archivi ZIP) vengono analizzati prima dell'apertura:

1. **Dimensione decompressa**: calcolata dalla somma delle dimensioni dichiarate
2. **Ratio compressione**: rapporti > 100:1 sono sospetti
3. **Limite configurabile**: default 100 MB decompresso

File sospetti vengono rifiutati con errore `SIZ-04`.

### Sanificazione nomi file

I nomi degli allegati email vengono sanificati automaticamente:

| Problema | Azione |
|----------|--------|
| Path traversal (`../`, `/etc/passwd`) | Estratto solo il nome file |
| Percorsi assoluti (`C:\Windows\...`) | Estratto solo il nome file |
| Caratteri di controllo (`\x00`, `\x1f`) | Sostituiti con `_` |
| Caratteri non validi (`<>:"/\|?*`) | Sostituiti con `_` |
| Nomi riservati Windows (`CON`, `LPT1`, etc.) | Prefisso `_` aggiunto |
| Spazi/punti finali | Rimossi |
| Nome troppo lungo (> 255 byte UTF-8) | Troncato preservando l'estensione |
| Encoding RFC 2047/2231 | Decodificato automaticamente |
| Unicode non normalizzato | Normalizzato a NFC |

Ogni sanificazione genera un **warning** con dettagli della modifica.

### Configurazione personalizzata

```python
from ingest import Ingestor, IngestConfig

# Configurazione restrittiva
config = IngestConfig(
    max_file_size_bytes=10 * 1024 * 1024,  # 10 MB
    max_email_total_size_bytes=20 * 1024 * 1024,  # 20 MB
    max_attachments=5,
    max_xlsx_decompressed_size_bytes=50 * 1024 * 1024,  # 50 MB
    reject_executables=True,  # Default: True
    reject_macros=True,  # Default: True
    warn_extension_mismatch=True,  # Default: True
    strict_mode=False,  # Se True, anche i warning bloccano
)

ingestor = Ingestor(config=config)
result = ingestor.ingest("documento.pdf")

# Verifica se ci sono stati errori critici
error_warnings = [w for w in result.warnings if w.severity.value == "ERROR"]
if error_warnings:
    print("File rifiutato:")
    for w in error_warnings:
        print(f"  [{w.code}] {w.message}")
```

### Codici di errore sicurezza

| Codice | Significato |
|--------|-------------|
| `SIZ-01` | File troppo grande |
| `SIZ-02` | Email troppo grande (totale) |
| `SIZ-03` | Troppi allegati |
| `SIZ-04` | Possibile zip bomb |
| `TYP-01` | Estensione non corrisponde al tipo rilevato |
| `TYP-02` | Tipo file non supportato |
| `TYP-03` | File eseguibile rifiutato |
| `TYP-04` | File con macro rifiutato |
| `NAM-01` | Nome file sanificato |
| `NAM-02` | Path traversal rimosso |
| `NAM-03` | Nome riservato Windows |
| `NAM-04` | Nome troncato |

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

#### Sicurezza (v1.1.0)

| Codice | Severità | Significato |
|--------|----------|-------------|
| `SIZ-01` | ERROR | File troppo grande |
| `SIZ-02` | ERROR | Email troppo grande (totale) |
| `SIZ-03` | ERROR | Troppi allegati |
| `SIZ-04` | ERROR | Possibile zip bomb rilevata |
| `TYP-01` | WARNING | Estensione non corrisponde al tipo rilevato |
| `TYP-02` | ERROR | Tipo file non supportato |
| `TYP-03` | ERROR | File eseguibile rifiutato |
| `TYP-04` | ERROR | File con macro rifiutato |
| `NAM-01` | WARNING | Nome file sanificato |
| `NAM-02` | WARNING | Path traversal rimosso |
| `NAM-03` | WARNING | Nome riservato Windows rinominato |
| `NAM-04` | WARNING | Nome file troncato |

#### Parser

| Codice | Severità | Significato |
|--------|----------|-------------|
| `PDF-01` | WARNING | PDF scansionato, richiede OCR |
| `PDF-02` | WARNING | Errore nel parsing PDF |
| `PDF-03` | WARNING | Errore estrazione tabelle |
| `XLS-01` | WARNING | Errore parsing Excel |
| `XLS-02` | WARNING | Libreria xlrd mancante |
| `XLS-03` | WARNING | Errore parsing file .xls |
| `CSV-01` | WARNING | Errore parsing CSV |
| `ATT-01` | WARNING | Tipo allegato non supportato |
| `ATT-02` | WARNING | Errore parsing allegato |
| `ATT-03` | WARNING | Allegato ignorato |

## Test

Esegui i test con pytest:

```bash
# Tutti i test
pytest tests/ -v

# Solo test di ingestione
pytest tests/test_ingest.py -v

# Solo test di sicurezza (v1.1.0)
pytest tests/test_security.py -v

# Solo test veloci
pytest tests/test_ingest.py -v -k "not TestAllSyntheticDocuments"

# Test su tutti i 150 documenti sintetici
pytest tests/test_ingest.py -v -k "TestAllSyntheticDocuments"

# Test con copertura
pytest tests/ -v --cov=ingest --cov-report=term-missing
```

I test verificano:
- Ingestione senza errori di tutti i 150 ordini sintetici
- Validazione dell'output contro lo schema JSON
- Estrazione di parti, testo e tabelle
- Coerenza con il ground truth (numero righe, etc.)
- Gestione di casi limite ed errori

### Test di sicurezza (v1.1.0)

Il file `tests/test_security.py` include test specifici per:
- Rilevamento tipo file via magic number
- Rilevamento mismatch estensione/contenuto
- Identificazione file pericolosi (eseguibili, macro)
- Sanificazione nomi file (path traversal, caratteri speciali, Unicode)
- Protezione zip bomb
- Limiti dimensione file ed email
- Test con file malevoli sintetici costruiti nei test

## Struttura del modulo

```
ingest/
├── __init__.py         # Export pubblici
├── __main__.py         # CLI
├── config.py           # Configurazione limiti (v1.1.0)
├── security.py         # Validazione e sanificazione (v1.1.0)
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
4. **Macro Excel**: rifiutate per sicurezza (configurabile con `reject_macros=False`)

## Sviluppi futuri

- [ ] Integrazione OCR (Tesseract) per PDF scansionati
- [ ] Supporto file .doc/.docx
- [ ] Estrazione immagini da PDF
- [ ] Riconoscimento layout documenti strutturati
- [ ] Analisi antivirus/sandboxing opzionale per allegati
