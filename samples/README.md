# Esempi di export

Questa cartella contiene esempi di output nei formati supportati:

| File | Formato | Descrizione |
|------|---------|-------------|
| `sample.generic.csv` | CSV | Export generico per import in altri sistemi |
| `sample.x12.850.txt` | X12 850 | EDI ANSI X12 versione 004010 |
| `sample.edifact.orders.txt` | EDIFACT ORDERS | UN/EDIFACT D.96A |
| `sample.peppol-order.xml` | Peppol BIS Order 3 | UBL 2.1 Order |

## Script di generazione

- `gen_samples.py` — Genera CSV, X12 850 e EDIFACT ORDERS da un file VOF
- `gen_peppol.py` — Genera Peppol BIS Order 3 da un file VOF

### Utilizzo

```bash
# Richiede: lxml (per Peppol)
pip install lxml

# Genera tutti i formati (eccetto Peppol)
python gen_samples.py ../schema/example-mro.json

# Genera Peppol Order
python gen_peppol.py ../schema/example-mro.json
```

## Note

- Tutti i dati sono **sintetici** (fittizi)
- I GLN sono generati con cifra di controllo GS1 valida
- I file X12 e EDIFACT sono validati solo per struttura, non certificati per uso reale
