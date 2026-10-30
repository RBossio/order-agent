# Configurazione

Questa cartella contiene i file di configurazione YAML:

- `thresholds.yaml` — soglie per score e decisioni (tolleranza prezzi, date PO, AUTO_POST, …)
- `rules.yaml` — regole disabilitate, override di severità, mappa spese → SKU servizio. `SEC-01`, `DUP-01` e `DUP-02` non sono disattivabili (`§7.1`).
- `odoo.conf.template` — template di configurazione Odoo (segreti da ambiente)
- `uom_crosswalk.yaml` — mapping delle unità di misura (previsto)
- `edi_partners.yaml` — profili EDI per partner (previsto)
- `mro_lexicon.yaml` — lessico MRO/JanSan per il matching (previsto)
