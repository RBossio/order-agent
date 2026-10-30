# Report Valutazione Estrazione Ordini

**Data:** 2026-10-30 09:33:06
**Modello:** ollama/qwen2.5:3b-instruct (Q4_K_M, 1.9 GB)
**Hardware:** Intel Xeon 4 cores, 15 GB RAM, CPU-only (no GPU)
**Pipeline:** ingest (file sintetico) → extract (Ollama, `temperature=0`, `repeat_penalty=1.1`, `num_predict=2048`, `format=json`)
**Campione:** 50/150 ordini stratificati (tutti i 22 casi difficili + 28 normali). Non è stato possibile valutare tutti i 150 ordini: ~56 s/ordine su CPU, stima ~2.3 ore sul dataset completo.

`qwen2.5:7b-instruct` è stato scaricato ma scartato: ~111 s/ordine su questa VM (troppo lento per 50+ documenti).

## Riepilogo vs target

| Metrica | Valore | Target |
|---------|--------|--------|
| Accuratezza testata | **56.0%** | ≥98% ❌ |
| Accuratezza righe | **36.9%** | ≥90% ❌ |
| Errori silenziosi | **149** (13.42%) | ≤1% ❌ |
| Ordini valutati | 50 | - |
| Fallimenti estrazione | 13 | - |
| Casi difficili | 22 (44.0%) | - |

## Accuratezza per Formato

| Formato | Ordini | Testata | Righe |
|---------|--------|---------|-------|
| EML | 19 | 43.4% | 10.7% |
| PDF | 18 | 66.7% | 44.4% |
| XLSX | 13 | 59.6% | 98.9% |

## Accuratezza per Tipo di Caso

| Tipo | Ordini | Testata | Righe |
|------|--------|---------|-------|
| Normali | 28 | 59.8% | 41.4% |
| Difficili | 22 | 51.1% | 32.9% |

## Accuratezza Campi Testata

| Campo | Corretti | Totali | Accuratezza |
|-------|----------|--------|-------------|
| po_number | 9 | 50 | 18.0% |
| po_date | 35 | 50 | 70.0% |
| currency | 50 | 50 | 100.0% |
| requested_delivery_date | 18 | 50 | 36.0% |

## Errori silenziosi

Campi errati con confidenza ≥80% e senza avviso di validazione.

| Ordine | Campo | Atteso | Estratto | Confidenza |
|--------|-------|--------|----------|------------|
| 42b2b9fb... | /header/po_number | NMC-01006 | From | 95% |
| f4403793... | /header/po_number | BW-01015 | PO | 95% |
| 06a6174f... | /header/po_number | MBM01018 | From | 95% |
| 06a6174f... | /lines/1/seller_item_code | FST-FWS-34-10-1 | FST-FWS-34-10 | 100% |
| 06a6174f... | /lines/4/quantity | 4 | 2.0 | 100% |
| 06a6174f... | /lines/4/seller_item_code | FST-SHC-12-13-2 | JAN-FTI-167 | 100% |
| 06a6174f... | /lines/6/quantity | 24 | 5.0 | 100% |
| 06a6174f... | /lines/6/seller_item_code | PPE-GLV-NIT-8-S-WHI | ABR-COW-6IN-5 | 100% |
| 06a6174f... | /lines/8/quantity | 2 | 6.0 | 100% |
| 06a6174f... | /lines/8/seller_item_code | JAN-LNR-3858-12-BL | JAN-FPD-20-BL | 100% |
| c6779f2b... | /header/po_number | PTD-01032 | From | 95% |
| 0349b447... | /header/po_number | PTD-01041 | From | 95% |
| 0349b447... | /lines/0/quantity | 3 | 10.0 | 100% |
| 0349b447... | /lines/0/seller_item_code | JAN-FST-181 | ABR-COW-4IN-1 | 100% |
| 6530d57f... | /header/po_number | FCH-01063 | PO | 95% |
| 6530d57f... | /lines/0/quantity | 1 | 2.0 | 100% |
| 6530d57f... | /lines/1/quantity | 4 | 8.0 | 100% |
| 6530d57f... | /lines/2/quantity | 2 | 4.0 | 100% |
| 6530d57f... | /lines/3/quantity | 3 | 6.0 | 100% |
| 6530d57f... | /lines/4/quantity | 6 | 12.0 | 100% |
| 6530d57f... | /lines/5/quantity | 3 | 6.0 | 100% |
| 6530d57f... | /lines/6/quantity | 4 | 8.0 | 100% |
| 6530d57f... | /lines/7/quantity | 24 | 48.0 | 100% |
| 6530d57f... | /lines/8/quantity | 24 | 48.0 | 100% |
| 6530d57f... | /lines/9/quantity | 4 | 8.0 | 100% |
| ... | (124 altri) | | | |

## Dettaglio Casi Difficili

| Ordine | Tipo | Testata | Righe GT | Righe Match |
|--------|------|---------|----------|-------------|
| 42b2b9fb... | MISSING_DATE, MISSING_QTY | 75% | 7 | 4 |
| f4403793... | QTY_WORDS | 50% | 11 | 0 |
| 06a6174f... | MULTIPAGE_PDF | 75% | 15 | 6 |
| 343c9ff6... | DATE_FORMAT | 25% | 9 | 9 |
| c6779f2b... | MISSING_PO_NUMBER | 50% | 2 | 2 |
| 0349b447... | TYPO_DESC | 50% | 4 | 3 |
| 55f0fd82... | MISSING_PO_NUMBER, DATE_FORMAT | 25% | 17 | 17 |
| 367884f8... | UOM_CONVERSION | 75% | 6 | 6 |
| 6530d57f... | EMAIL_CONTRADICTORY | 50% | 12 | 0 |
| 36137ae4... | MULTIPAGE_PDF, CUSTOMER_CODES | 50% | 2 | 2 |
| 47cfb927... | CUSTOMER_CODES | 25% | 22 | 0 |
| 0bcf5cc6... | EMAIL_CONTRADICTORY, MISSING_DATE | 25% | 11 | 0 |
| 4d5faf75... | TOTAL_MIXED | 75% | 7 | 2 |
| 708c2e7d... | MISSING_QTY | 75% | 11 | 6 |
| 5a5c9563... | MISSING_PO_NUMBER | 50% | 3 | 1 |
| 5d391dd4... | AMBIGUOUS_DESC | 25% | 25 | 0 |
| 4d78ca32... | CUSTOMER_CODES | 75% | 4 | 2 |
| 74b0cb67... | MISSING_DATE | 50% | 18 | 7 |
| 0214ff9f... | TYPO_DESC, TOTAL_MIXED | 75% | 3 | 2 |
| 5f2b3be7... | TYPO_DESC | 25% | 21 | 0 |

## Performance

| Metrica | Valore |
|---------|--------|
| Tempo totale | 2809.8 s (46.8 min) |
| Tempo medio/ordine | 56.2 s |
| Chiamate LLM | 37 (13 timeout, fallback preprocessor) |

## Errori principali

1. **Numero PO catturato male (18%)**: il regex della pre-elaborazione su testo libero prendeva token tipo `PO` / `From` da frasi (`Please process the following order`). Corretto dopo la run (`PO Number:` + almeno una cifra); i numeri sopra restano quelli misurati.
2. **Email (10.7% righe)**: liste in testo libero, quantità in parole (`QTY_WORDS`), allegati contraddittori (`EMAIL_CONTRADICTORY`). Il 3B spesso va in timeout o produce JSON incompleto.
3. **PDF multipagina / tabelle rumorose**: il preprocessor mappa colonne in modo parziale; l'LLM non completa le righe mancanti entro 2048 token.
4. **Data di consegna (36%)**: campo assente o in formato diverso da quello in ground truth.
5. **Timeout LLM (13/50)**: `num_predict=2048` e timeout 90 s hanno evitato i loop di ripetizione della run precedente, ma su documenti lunghi la chiamata fallisce; in quel caso si usa solo la pre-elaborazione e l'ordine viene contato (non scartato).

## Confronto con i target

Nessun target è stato raggiunto con `qwen2.5:3b-instruct` su CPU:

| Target | Misurato | Esito |
|--------|----------|-------|
| Testata ≥ 98% | 56.0% | Non raggiunto |
| Righe ≥ 90% | 36.9% (XLSX 98.9%) | Non raggiunto in aggregato |
| Errori silenziosi ≤ 1% | 13.42% | Non raggiunto |

La pre-elaborazione tabellare su Excel è già al target righe. Il gap è su EML/PDF e sulla testata (PO number + date di consegna), più la confidenza alta assegnata a campi sbagliati senza avviso.
