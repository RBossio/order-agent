# Dati Master Sintetici - VentureOrder

Questa cartella contiene il generatore e i dati master sintetici per VentureOrder.
I dati sono la **singola fonte di verità** per il prototipo e possono essere riusati
dal generatore di ordini sintetici.

## Struttura

```
datagen/
├── README.md                    # Questo file
├── generate_master_data.py      # Script generatore (seed deterministico)
└── master/                      # Dati generati (JSON)
    ├── manifest.json            # Metadati e conteggi
    ├── products.json            # 300 articoli MRO/JanSan
    ├── customers.json           # 10 clienti fittizi
    ├── customer_xref.json       # Cross-reference cliente→SKU
    └── uom_definitions.json     # Definizioni UoM con mappatura Rec20/X12
```

## Generazione

```bash
python datagen/generate_master_data.py
```

I dati sono **deterministici** (seed fisso = 42). Rigenerando si ottengono gli stessi dati.

## Formato dei file

### products.json

Array di 300 prodotti MRO/JanSan sintetici.

```json
{
  "default_code": "FST-HCS-12-13X2",
  "name": "Hex Cap Screw 1/2-13 x 2 Grade 5 Zinc (SYNTHETIC)",
  "category": "Fasteners",
  "sale_uom": "BX",
  "list_price": 18.75,
  "gtin": "9999900000010",
  "manufacturer_code": "ACME-12345",
  "manufacturer_name": "ACME Industrial (fictitious)",
  "pack_description": "BX/50",
  "conversions": [
    {"from_uom": "BX", "to_uom": "EA", "factor": 50.0}
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `default_code` | string | SKU distributore (univoco) |
| `name` | string | Nome prodotto con "(SYNTHETIC)" |
| `category` | string | Categoria MRO/JanSan |
| `sale_uom` | string | Unità di vendita (codice Rec20: EA, BX, CS, PK, CT, DZN, GLL, RO, PR, BG, DR) |
| `list_price` | number | Prezzo di listino USD |
| `gtin` | string | GTIN-13 con check digit valido |
| `manufacturer_code` | string | Codice produttore |
| `manufacturer_name` | string | Nome produttore fittizio |
| `pack_description` | string \| null | Descrizione confezione (es. "BX/50", "4/1GAL", "100/BX 10BX/CS") |
| `conversions` | array | Conversioni UoM (da → a con fattore) |

### customers.json

Array di 10 clienti fittizi.

```json
{
  "ref": "C-ACME",
  "name": "Acme Manufacturing Inc. (SYNTHETIC)",
  "tax_id": "12-3456789",
  "email": "purchasing@acme.example",
  "phone": "+1-555-1234",
  "billing_address": {
    "line1": "1200 Industrial Pkwy",
    "city": "Toledo",
    "region": "OH",
    "postal_code": "43601",
    "country": "US"
  },
  "shipping_addresses": [
    { "line1": "...", "city": "...", "region": "...", "postal_code": "...", "country": "US" }
  ],
  "pricelist_name": "Acme Pricelist"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `ref` | string | Codice cliente (es. "C-ACME") |
| `name` | string | Ragione sociale con "(SYNTHETIC)" |
| `tax_id` | string | EIN fittizio (formato XX-XXXXXXX) |
| `email` | string | Email con dominio `.example` (RFC 2606) |
| `phone` | string | Telefono fittizio |
| `billing_address` | object | Indirizzo di fatturazione |
| `shipping_addresses` | array | 1-3 indirizzi di spedizione |
| `pricelist_name` | string | Nome del listino associato |

### customer_xref.json

Array di cross-reference codice cliente → SKU distributore.
Circa il 70% delle combinazioni cliente×prodotto.

```json
{
  "customer_ref": "C-ACME",
  "customer_item_code": "ACME-FST-0412",
  "product_sku": "FST-HCS-12-13X2",
  "customer_uom": "BX",
  "customer_description": "Hex Cap Screw 1/2-13 x 2 Grade 5 Zinc"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `customer_ref` | string | Riferimento al cliente |
| `customer_item_code` | string | Codice articolo del cliente (part number interno) |
| `product_sku` | string | SKU distributore (default_code) |
| `customer_uom` | string | UoM usata dal cliente (può differire da sale_uom) |
| `customer_description` | string \| null | Descrizione usata dal cliente |

### uom_definitions.json

Definizioni UoM con mappatura tra codici Rec20, X12 e Odoo.

```json
{
  "category_unit": {
    "name": "Unit",
    "uoms": [
      {"code": "EA", "name": "Units", "factor": 1.0, "rec20": "EA", "x12": "EA"},
      {"code": "DZN", "name": "Dozens", "factor": 12.0, "rec20": "DZN", "x12": "DZ"},
      ...
    ]
  },
  "category_packaging": {
    "name": "Packaging",
    "uoms": [
      {"code": "BX", "name": "Box", "factor": 1.0, "rec20": "BX", "x12": "BX"},
      {"code": "CS", "name": "Case", "factor": 1.0, "rec20": "CS", "x12": "CA"},
      ...
    ]
  },
  ...
}
```

## Mappatura UoM (da §8.7 architettura)

| VOF (Rec 20) | Significato | X12 (355) | EDIFACT/Peppol | Odoo |
|--------------|-------------|-----------|----------------|------|
| EA | pezzo | EA | EA | Units |
| BX | scatola | BX | BX | Box |
| CS | cartone/cassa | CA | CS | Case |
| PK | confezione | PK | PK | Pack |
| CT | cartone | CT | CT | Carton |
| DZN | dozzina | DZ | DZN | Dozens |
| GLL | gallone US | GA | GLL | gal (US) |
| LTR | litro | LT | LTR | L |
| RO | rotolo | RL | RO | Roll |
| PR | paio | PR | PR | Pair |
| BG | sacco | BG | BG | Bag |
| DR | fusto | DR | DR | Drum |

## Uso nei test

I dati master sono progettati per essere riusati:

1. **Seed Odoo**: `scripts/seed_odoo.py` carica i dati in Odoo
2. **Generatore ordini**: può importare `products.json` e `customer_xref.json`
3. **Test di matching**: usa `customer_xref.json` per validare il riconoscimento articoli
4. **Conversioni UoM**: usa `products.conversions` per validare le conversioni

## Convenzioni

- Tutti i nomi contengono "(SYNTHETIC)" o "(fictitious)"
- I domini email usano `.example` (RFC 2606)
- I GTIN hanno prefisso 999990 (riservato per test)
- Gli EIN sono nel formato corretto ma fittizi
- I GLN nei sample Peppol hanno prefisso 99999 (non reali)
