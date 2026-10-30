# Harness di valutazione

Valutazione extract riproducibile:

```bash
make eval
```

Seed 42, `qwen2.5:3b-instruct`, temperature=0, repeat_penalty=1.1, num_predict=2048, niente PDF. Produce `docs/eval/eval_results.json` (dettaglio per ordine, chiamate/timeout LLM, numeri «prima» da `git show 380c7bb:docs/eval/eval_results.json`) e la stessa run con LLM spento.

Script per misurare i KPI del prototipo:

- Accuratezza dei campi (target ≥ 98%)
- Righe completamente corrette (target ≥ 90%)
- Errori silenziosi (target ≤ 1%)
- Latenza email → bozza (target < 60s p95)

## Riconoscimento clienti e articoli

Valutazione offline sul dataset sintetico (nessuna rete, nessun LLM).
Il matcher **non** legge gli ID attesi (`buyer.resolved`, `code_on_document`,
`line.resolution` / `sku`): solo i campi del documento, elencati in
`src/ventureorder/match/fields.py`.

```bash
python eval/match_eval.py              # set pulito + set rumoroso
python eval/match_eval.py --set clean
python eval/match_eval.py --set noisy
python eval/match_eval.py --json
```

Per ciascun set riporta:

- **precisione esclusi gli ambigui** (risolti univoci: correct / (correct + incorrect))
- **accuratezza top-1 su tutte le righe con uno SKU proposto** (`to_vof()` scrive
  lo SKU anche sul FUZZY ambiguo)
- **ambigue sbagliate** (top-1 diverso dal ground truth)
- **recall@3** (codice giusto tra i primi 3 candidati, o SKU univoco corretto)
- **copertura** (risolti univoci / totale)
- **percentuale di ambigui**
- **errori con confidenza ≥ 0,9**, **≥ REVIEW (0,92)** e **≥ AUTO (0,97)**

Il set rumoroso (validazione seed 42, taratura seed 7/13/99) usa i casi
difficili, varianti e **ordini extra generati con quegli seed**: niente P.IVA,
email su dominio generico, nome con refusi/abbreviazioni, codici cliente
sconosciuti, codici con spazi/trattini, descrizioni parafrasate, UoM diverse.
Un esito ambiguo non ha mai confidenza alta; il FUZZY è limitato a 0,85 salvo
conferme indipendenti (UoM, prezzo, misura/colore). I test impongono errori
articoli ≥ 0,9 = 0% (1 punto di margine sul target ≤ 1%).

```bash
python eval/match_eval.py --calibrate   # soglie sui seed 7, 13, 99
```
