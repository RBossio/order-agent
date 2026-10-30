# Report Valutazione Estrazione Ordini

**Data:** 2026-10-30 12:03:32
**Modello:** ollama/qwen2.5:3b-instruct
**Hardware:** Intel Xeon 4 cores, 15GB RAM, CPU-only (no GPU)

## Riepilogo vs target

| Metrica | Valore | Target |
|---------|--------|--------|
| Accuratezza testata | **85.0%** | ≥98% ❌ |
| Accuratezza righe | **47.3%** | ≥90% ❌ |
| Errori silenziosi (ordini AUTO_POST) | **0/28** (0.00%) | ≤1% ✅ |
| Errori silenziosi (campi, solo AUTO_POST) | **0** (0.00%) | metrica separata |
| AUTO_POST | **28/50** (56.0%) | - |
| REVIEW | **22/50** (44.0%) | - |
| REJECT | **0/50** (0.0%) | - |
| Tempo medio/ordine | **43.0s** | - |
| Ordini valutati | 50 | - |
| Fallimenti estrazione | 21 | - |
| Timeout LLM | 21 | - |
| Chiamate LLM | 4 | - |
| Casi difficili | 12 (24.0%) | - |

Errore silenzioso = ordine in **AUTO_POST** con almeno un campo sbagliato (testata, codice/qty/UoM/prezzo/codice cliente di riga, righe in più o mancanti, valori inventati se la ground truth è vuota). La percentuale a livello di campo è una metrica separata, calcolata solo sugli ordini AUTO_POST.

## Accuratezza per Formato

| Formato | Ordini | Testata | Righe | Silent ordini | Silent campi | AUTO_POST | REVIEW | REJECT |
|---------|--------|---------|-------|---------------|--------------|-----------|--------|--------|
| EML | 25 | 70.0% | 24.8% | 0 | 0 | 3/25 | 22/25 | 0/25 |
| XLSX | 25 | 100.0% | 98.7% | 0 | 0 | 25/25 | 0/25 | 0/25 |

## Accuratezza per Tipo di Caso

| Tipo | Ordini | Testata | Righe |
|------|--------|---------|-------|
| Normali | 38 | 83.6% | 39.1% |
| Difficili | 12 | 89.6% | 76.3% |

## Accuratezza Campi Testata

| Campo | Corretti | Totali | Accuratezza |
|-------|----------|--------|-------------|
| po_number | 50 | 50 | 100.0% |
| po_date | 33 | 50 | 66.0% |
| currency | 50 | 50 | 100.0% |
| requested_delivery_date | 37 | 50 | 74.0% |

## Dettaglio Casi Difficili

| Ordine | Tipo | Testata | Righe GT | Righe Match |
|--------|------|---------|----------|-------------|
| e735b08f... | QTY_WORDS | 100% | 20 | 20 |
| 55b7e9d3... | MISSING_DATE, UNKNOWN_CUSTOMER_CODE | 50% | 14 | 0 |
| d04956bd... | QTY_WORDS | 75% | 7 | 6 |
| 06a6174f... | CUSTOMER_CODES | 100% | 9 | 9 |
| a3f01208... | MISSING_DATE | 100% | 15 | 15 |
| 13c628cc... | TOTAL_MIXED | 100% | 5 | 5 |
| e5b2065c... | AMBIGUOUS_DESC | 100% | 4 | 3 |
| b88bea77... | EMAIL_CONTRADICTORY | 100% | 12 | 12 |
| 367884f8... | PRICE_OUT_OF_TOLERANCE | 100% | 13 | 13 |
| 00c240fa... | AMBIGUOUS_DESC | 100% | 3 | 2 |
| 9c75d2a9... | TOTAL_MIXED | 100% | 2 | 2 |
| ed19ba0b... | UOM_CONVERSION | 50% | 10 | 0 |

## Performance

- Tempo totale: 2151.2s
- Tempo medio per ordine: 43024ms
- Chiamate LLM totali: 4

## Prima / dopo

Prima: stesso campione (50 ordini, senza PDF, senza LLM) sul codice di main prima di questa PR (`aea6f9b`). Testata 25,0%, righe 41,5% (XLSX 96,8%, EML 17,3%), AUTO_POST 0/50.
Dopo (senza LLM): questo commit, stesso seed e stessi documenti. Campione senza PDF.

| Metrica | Prima | Dopo (senza LLM) |
|---------|-------|------------------|
| Testata | 25.0% | 83.0% |
| Righe | 41.5% | 44.4% |
| AUTO_POST | 0/50 | 29/50 |
| REVIEW | 50/50 | 21/50 |
| REJECT | 0/50 | 0/50 |
| Errori silenziosi (ordini AUTO_POST) | 0/0 | 0/29 |

### Per formato

| Formato | Testata prima | Testata dopo | Righe prima | Righe dopo | AUTO_POST dopo | REVIEW dopo | REJECT dopo | Silent ordini dopo |
|---------|---------------|--------------|-------------|------------|----------------|--------------|--------------|--------------------|
| EML | — | 66.0% | 17.3% | 20.6% | 4/25 | 21/25 | 0/25 | 0 |
| XLSX | — | 100.0% | 96.8% | 98.7% | 25/25 | 0/25 | 0/25 | 0 |

## Contributo LLM

Stessa run (stesso campione, stessi documenti) con LLM disattivato: solo preprocessor.

| Metrica | Con LLM | Senza LLM |
|---------|---------|-----------|
| Testata | 85.0% | 83.0% |
| Righe | 47.3% | 44.4% |
| AUTO_POST | 28/50 | 29/50 |
| REVIEW | 22/50 | 21/50 |
| Chiamate LLM | 4 | 0 |
| Timeout LLM | 21 | 0 |

## (b) Cosa aspettarsi su documenti reali

I numeri sopra sono su **PO sintetici**: Excel con colonne etichettate, email generate da cinque template noti a questo repo, anagrafica completa, prezzi allineati al listino. Non sono un campione di PO veri.

**Excel/CSV strutturati.** È la fascia in cui il prototipo è già utile: testata e righe escono dal preprocessor, AUTO_POST è raggiungibile se cliente e articoli sono in anagrafica. Su file reali manca lo sporco che qui non c'è (fogli multipli, intestazioni su due righe, colonne fuori ordine, prezzi in millesimi, UoM inventate).

**Email di testo libero.** Le regex attuali riconoscono solo `N. [SKU]` + `Qty:`. I cinque template nuovi (prosa, tabella HTML, elenco in firma, quantità in lettere, inoltro) sono volutamente fuori da quelle regex: servono all'LLM. Su questa macchina `qwen2.5:3b-instruct` in CPU va in timeout sulla maggior parte delle email (21/25 in questo campione). Senza un modello che risponda in tempo, quelle email restano in REVIEW con testata/righe incomplete. Su documenti veri (inoltri, firme, HTML di Outlook) l'accuratezza sarà quella dell'LLM, non quella dell'Excel.

**PDF.** Esclusi da questo run. Il preprocessor legge tabelle pdfplumber; i PDF scansionati (`needs_ocr`) non sono supportati.

**Limiti noti.** Matching articoli solo SKU/xref esatto; niente fuzzy. `make eval` attiva `CatalogMatcher(allowlist_synthetic=True)` solo per questa misura: in UI e in produzione l'allowlist è quella reale (§7.1 ALLOWLIST+HISTORY). Un ordine pulito di un cliente nuovo va in REVIEW. Valuta assente dal documento: anagrafica cliente (fonte `catalog`, 0,97) oppure default USD a 0,50 → REVIEW. Confidenza deterministica 0,98, soglia AUTO_POST 0,97 invariata.
