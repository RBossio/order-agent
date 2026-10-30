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

Valutazione offline sul dataset sintetico (nessuna rete, nessun LLM):

```bash
python eval/match_eval.py
python eval/match_eval.py --json
```

Riporta la **precisione** (percentuale di clienti/articoli risolti correttamente) e la copertura. I test in `tests/test_match_eval.py` rieseguono lo stesso calcolo.
