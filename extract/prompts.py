"""
Prompt e schema JSON per l'estrazione ordini.

Definisce il prompt di sistema, il formato di output e lo schema JSON
per vincolare la risposta del modello.
"""

from __future__ import annotations

EXTRACTION_SYSTEM_PROMPT = """Sei un assistente specializzato nell'estrazione di dati da ordini d'acquisto (Purchase Orders).

Il tuo compito è estrarre le informazioni strutturate da un documento d'ordine e restituirle in formato JSON.

REGOLE FONDAMENTALI:
1. Estrai SOLO le informazioni presenti nel documento, non inventare dati
2. Se un campo non è presente, omettilo o usa null
3. Mantieni i codici articolo ESATTAMENTE come scritti (inclusi trattini, spazi)
4. Per le date, preserva il formato originale se non ambiguo
5. Per le quantità, usa numeri (non parole)
6. Per l'unità di misura (UoM), usa il codice breve (EA, CS, BX, PK, etc.)
7. Per i prezzi, usa numeri senza simbolo di valuta

STRUTTURA OUTPUT JSON:
{
  "header": {
    "po_number": "numero ordine",
    "po_date": "data ordine",
    "currency": "USD|EUR|...",
    "requested_delivery_date": "data consegna richiesta",
    "buyer_reference": "riferimento acquirente/reparto",
    "payment_terms": "termini pagamento",
    "ship_via": "metodo spedizione",
    "notes": "note generali"
  },
  "buyer": {
    "name": "nome azienda cliente",
    "code": "codice cliente",
    "address": "indirizzo completo",
    "contact_name": "nome contatto",
    "contact_email": "email contatto"
  },
  "ship_to": {
    "name": "destinazione spedizione",
    "address": "indirizzo spedizione"
  },
  "lines": [
    {
      "line_no": 1,
      "seller_item_code": "codice fornitore",
      "buyer_item_code": "codice cliente",
      "description": "descrizione articolo",
      "quantity": 10,
      "uom_raw": "EA",
      "unit_price": 25.50,
      "line_amount": 255.00
    }
  ],
  "totals": {
    "subtotal": 255.00,
    "tax": 20.40,
    "total": 275.40
  }
}"""

EXTRACTION_USER_PROMPT_TEMPLATE = """Estrai i dati dell'ordine dal seguente documento.

{preprocessed_context}

=== CONTENUTO DOCUMENTO ===
{document_content}
=== FINE DOCUMENTO ===

Rispondi SOLO con il JSON strutturato, senza spiegazioni aggiuntive."""

EXTRACTION_RETRY_PROMPT_TEMPLATE = """La risposta precedente non era un JSON valido.

Errore di validazione: {error_message}

Correggi il JSON e rispondi nuovamente. Assicurati che:
1. Sia un JSON valido (parentesi bilanciate, virgole corrette)
2. I numeri non abbiano simboli di valuta
3. Le stringhe siano tra doppi apici

Documento originale (riepilogo):
{document_summary}

Rispondi SOLO con il JSON corretto."""

EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "header": {
            "type": "object",
            "properties": {
                "po_number": {"type": "string"},
                "po_date": {"type": "string"},
                "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
                "requested_delivery_date": {"type": ["string", "null"]},
                "buyer_reference": {"type": ["string", "null"]},
                "payment_terms": {"type": ["string", "null"]},
                "ship_via": {"type": ["string", "null"]},
                "notes": {"type": ["string", "null"]},
            },
            "required": ["po_number", "po_date"],
        },
        "buyer": {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "code": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
                "contact_name": {"type": ["string", "null"]},
                "contact_email": {"type": ["string", "null"]},
            },
        },
        "ship_to": {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
            },
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line_no": {"type": "integer", "minimum": 1},
                    "seller_item_code": {"type": ["string", "null"]},
                    "buyer_item_code": {"type": ["string", "null"]},
                    "description": {"type": "string"},
                    "quantity": {"type": "number", "exclusiveMinimum": 0},
                    "uom_raw": {"type": "string"},
                    "unit_price": {"type": ["number", "null"]},
                    "line_amount": {"type": ["number", "null"]},
                    "pack_info": {"type": ["string", "null"]},
                    "notes": {"type": ["string", "null"]},
                },
                "required": ["description", "quantity", "uom_raw"],
            },
        },
        "totals": {
            "type": "object",
            "properties": {
                "subtotal": {"type": ["number", "null"]},
                "tax": {"type": ["number", "null"]},
                "total": {"type": ["number", "null"]},
            },
        },
    },
    "required": ["header", "lines"],
}


def build_extraction_prompt(
    document_content: str,
    preprocessed_lines: list[dict] | None = None,
    preprocessed_header: dict | None = None,
) -> str:
    """
    Costruisce il prompt per l'estrazione.

    Args:
        document_content: Contenuto testuale del documento.
        preprocessed_lines: Righe già estratte dal preprocessor.
        preprocessed_header: Header già estratti dal preprocessor.

    Returns:
        Prompt completo per l'LLM.
    """
    context_parts = []

    if preprocessed_header:
        context_parts.append("DATI TESTATA GIÀ ESTRATTI:")
        for key, value in preprocessed_header.items():
            if value:
                context_parts.append(f"  - {key}: {value}")

    if preprocessed_lines:
        context_parts.append("\nRIGHE GIÀ ESTRATTE DA TABELLA:")
        context_parts.append("(Verifica e completa con dati mancanti)")
        for line in preprocessed_lines[:10]:
            line_str = f"  Riga {line.get('line_no', '?')}: "
            if line.get('seller_item_code'):
                line_str += f"[{line['seller_item_code']}] "
            line_str += f"{line.get('description', '?')} "
            line_str += f"Qty: {line.get('quantity', '?')} {line.get('uom_raw', '')}"
            context_parts.append(line_str)
        if len(preprocessed_lines) > 10:
            context_parts.append(f"  ... e altre {len(preprocessed_lines) - 10} righe")

    preprocessed_context = "\n".join(context_parts) if context_parts else "(Nessun dato pre-estratto)"

    content_truncated = document_content[:8000]
    if len(document_content) > 8000:
        content_truncated += "\n\n[... contenuto troncato ...]"

    return EXTRACTION_USER_PROMPT_TEMPLATE.format(
        preprocessed_context=preprocessed_context,
        document_content=content_truncated,
    )


def build_retry_prompt(error_message: str, document_summary: str) -> str:
    """Costruisce il prompt per il retry dopo errore di validazione."""
    return EXTRACTION_RETRY_PROMPT_TEMPLATE.format(
        error_message=error_message,
        document_summary=document_summary[:2000],
    )
