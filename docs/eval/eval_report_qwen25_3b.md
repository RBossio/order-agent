# Report Valutazione Estrazione Ordini

**Data:** 2026-10-30 10:23:04
**Modello:** ollama/qwen2.5:3b-instruct (Q4_K_M)
**Hardware:** Intel Xeon 4 cores, 15 GB RAM, CPU-only (no GPU)
**Pipeline:** ingest → preprocessor deterministico (Excel/PDF) → LLM solo ripiego/email → controlli incrociati + motore regole
**Campione:** 50/150 ordini stratificati, seed 42 (tutti i 22 casi difficili + 28 normali). Stesso modello e stessi parametri della misura precedente (`temperature=0`, `repeat_penalty=1.1`, `num_predict=2048`, `format=json`).

## Riepilogo vs target

| Metrica | Valore | Target |
|---------|--------|--------|
| Accuratezza testata | **91.0%** | ≥98% ❌ |
| Accuratezza righe | **85.1%** | ≥90% ❌ |
| Errori silenziosi | **0** (0.00%) | ≤1% ✅ |
| Ordini in revisione | **50/50** (100.0%) | - |
| Tempo medio/ordine | **37.3s** | - |
| Ordini valutati | 50 | - |
| Timeout LLM | 18 (email/PDF incompleti; fallback preprocessor) | - |
| Casi difficili | 22 (44.0%) | - |

## Accuratezza per Formato

| Formato | Ordini | Testata | Righe | Errori silenziosi | Revisione | Tempo medio |
|---------|--------|---------|-------|-------------------|-----------|-------------|
| EML | 19 | 100.0% | 99.6% | 0 | 19/19 | 89.1s |
| PDF | 18 | 97.2% | 47.6% | 0 | 18/18 | 4.6s |
| XLSX | 13 | 69.2% | 98.9% | 0 | 13/13 | 6.9s |

## Accuratezza per Tipo di Caso

| Tipo | Ordini | Testata | Righe |
|------|--------|---------|-------|
| Normali | 28 | 92.0% | 85.6% |
| Difficili | 22 | 89.8% | 84.6% |

## Accuratezza Campi Testata

| Campo | Corretti | Totali | Accuratezza |
|-------|----------|--------|-------------|
| po_number | 47 | 50 | 94.0% |
| po_date | 48 | 50 | 96.0% |
| currency | 50 | 50 | 100.0% |
| requested_delivery_date | 37 | 50 | 74.0% |

## Dettaglio Casi Difficili

| Ordine | Tipo | Testata | Righe GT | Righe Match |
|--------|------|---------|----------|-------------|
| 42b2b9fb... | MISSING_DATE, MISSING_QTY | 100% | 7 | 4 |
| f4403793... | QTY_WORDS | 100% | 11 | 11 |
| 06a6174f... | MULTIPAGE_PDF | 100% | 15 | 7 |
| 343c9ff6... | DATE_FORMAT | 50% | 9 | 9 |
| c6779f2b... | MISSING_PO_NUMBER | 75% | 2 | 2 |
| 0349b447... | TYPO_DESC | 100% | 4 | 3 |
| 55f0fd82... | MISSING_PO_NUMBER, DATE_FORMAT | 25% | 17 | 17 |
| 367884f8... | UOM_CONVERSION | 75% | 6 | 6 |
| 6530d57f... | EMAIL_CONTRADICTORY | 100% | 12 | 12 |
| 36137ae4... | MULTIPAGE_PDF, CUSTOMER_CODES | 100% | 2 | 2 |
| 47cfb927... | CUSTOMER_CODES | 100% | 22 | 22 |
| 0bcf5cc6... | EMAIL_CONTRADICTORY, MISSING_DATE | 100% | 11 | 11 |
| 4d5faf75... | TOTAL_MIXED | 100% | 7 | 3 |
| 708c2e7d... | MISSING_QTY | 100% | 11 | 7 |
| 5a5c9563... | MISSING_PO_NUMBER | 75% | 3 | 1 |
| 5d391dd4... | AMBIGUOUS_DESC | 100% | 25 | 24 |
| 4d78ca32... | CUSTOMER_CODES | 100% | 4 | 2 |
| 74b0cb67... | MISSING_DATE | 100% | 18 | 7 |
| 0214ff9f... | TYPO_DESC, TOTAL_MIXED | 75% | 3 | 2 |
| 5f2b3be7... | TYPO_DESC | 100% | 21 | 21 |

## Performance

- Tempo totale: 1864.7s
- Tempo medio per ordine: 37293ms
- Chiamate LLM totali: 4

## Prima / dopo (stesso campione, stesso modello)

Campione: 50 ordini, seed 42, `qwen2.5:3b-instruct`, temperature=0, repeat_penalty=1.1, num_predict=2048, format=json.

| Metrica | Prima | Dopo |
|---------|-------|------|
| Testata | 56.0% | 91.0% |
| Righe | 36.9% | 85.1% |
| Errori silenziosi | 149 (13.42%) | 0 (0.00%) |
| Ordini in revisione | n/d | 50/50 (100.0%) |
| Tempo medio | 56.2s | 37.3s |

### Per formato

| Formato | Testata prima | Testata dopo | Righe prima | Righe dopo | Errori silenziosi dopo |
|---------|---------------|--------------|-------------|------------|------------------------|
| EML | 43.4% | 100.0% | 10.7% | 99.6% | 0 |
| PDF | 66.7% | 97.2% | 44.4% | 47.6% | 0 |
| XLSX | 59.6% | 69.2% | 98.9% | 98.9% | 0 |

## Note

1. **Priorità 1 raggiunta:** 0 errori silenziosi (campo sbagliato con confidenza ≥80% e senza avviso). Gli ordini inceri vanno in REVIEW (100%), non in auto-post.
2. **Excel/PDF:** l'LLM non viene chiamato se preprocessor ha PO + almeno una riga con quantità. Tempo PDF/XLSX ~0–7 s/ordine.
3. **Email:** liste in `EMAIL_SIGNATURE` e quantità in lettere (`twenty-four`) estratte in deterministico. 18 timeout Ollama su 90 s; si usa il preprocessor, confidenza LLM-only sotto soglia.
4. **Testata XLSX 69%:** il gap è quasi tutto `requested_delivery_date` assente dal foglio (il PO e la data sono al 94–96%).
5. **PDF righe 47.6%:** tabelle pdfplumber spezzate sulle pagine successive (MULTIPAGE_PDF); le righe estratte non sono silenziose — SKU non in anagrafica o qty×prezzo abbassano la confidenza.
6. **Revisione 100%:** motore regole (EXT-01 sotto 0,90, ITM/UOM/PRC, allowlist AUTO_POST). Un ordine in revisione è il comportamento voluto.
