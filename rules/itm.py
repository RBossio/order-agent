"""ITM: Item/Product validation rules."""

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("ITM-01", Severity.BLOCK)
def itm_01_item_unresolved(ctx: RuleContext) -> list[Issue]:
    """Verifica che ogni articolo sia risolto in anagrafica."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        item = line.get("item", {})
        item_id = item.get("id") or item.get("item_id")
        resolution_status = item.get("resolution_status", "resolved")

        if resolution_status == "unresolved" or (not item_id and not item.get("description")):
            issues.append(
                Issue(
                    rule_id="ITM-01",
                    severity=Severity.BLOCK,
                    message=f"Riga {i + 1}: articolo non risolto",
                    json_pointer=f"/lines/{i}/item",
                    suggestion="Associare l'articolo a un codice in anagrafica",
                )
            )

    return issues


@rule("ITM-02", Severity.BLOCK)
def itm_02_item_archived(ctx: RuleContext) -> list[Issue]:
    """Verifica che l'articolo non sia archiviato/obsoleto."""
    lines = ctx.order.get("lines", [])
    ref = ctx.reference_data
    issues = []

    for i, line in enumerate(lines):
        item = line.get("item", {})
        item_id = item.get("id") or item.get("item_id")

        if item_id and ref:
            master_item = ref.get_item(item_id)
            if master_item and master_item.get("status") in ("archived", "obsolete", "discontinued"):
                issues.append(
                    Issue(
                        rule_id="ITM-02",
                        severity=Severity.BLOCK,
                        message=f"Riga {i + 1}: articolo '{item_id}' archiviato/obsoleto",
                        json_pointer=f"/lines/{i}/item/id",
                        suggestion="Sostituire con articolo attivo",
                        details={"status": master_item.get("status")},
                    )
                )

    return issues


@rule("ITM-03", Severity.REVIEW)
def itm_03_fuzzy_match(ctx: RuleContext) -> list[Issue]:
    """Segnala articoli risolti con match fuzzy."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        item = line.get("item", {})
        resolution_method = item.get("resolution_method")
        confidence = item.get("match_confidence", 1.0)

        if resolution_method == "fuzzy" or (confidence and confidence < 0.90):
            issues.append(
                Issue(
                    rule_id="ITM-03",
                    severity=Severity.REVIEW,
                    message=f"Riga {i + 1}: articolo risolto con match fuzzy ({confidence:.0%})",
                    json_pointer=f"/lines/{i}/item",
                    suggestion="Verificare l'associazione articolo",
                    details={"confidence": confidence},
                )
            )

    return issues


@rule("ITM-04", Severity.REVIEW)
def itm_04_conflicting_codes(ctx: RuleContext) -> list[Issue]:
    """Verifica conflitti tra codici articolo (GTIN, MPN, SKU)."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        item = line.get("item", {})
        gtin = item.get("gtin")
        mpn = item.get("mpn")
        sku = item.get("sku")
        item_id = item.get("id")

        codes_provided = sum(1 for c in [gtin, mpn, sku] if c)
        if codes_provided > 1 and item.get("code_conflict"):
            issues.append(
                Issue(
                    rule_id="ITM-04",
                    severity=Severity.REVIEW,
                    message=f"Riga {i + 1}: conflitto tra codici articolo",
                    json_pointer=f"/lines/{i}/item",
                    suggestion="Verificare GTIN, MPN e SKU",
                    details={"gtin": gtin, "mpn": mpn, "sku": sku, "resolved_id": item_id},
                )
            )

    return issues


@rule("ITM-05", Severity.WARN)
def itm_05_gtin_checksum(ctx: RuleContext) -> list[Issue]:
    """Verifica checksum del GTIN."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        item = line.get("item", {})
        gtin = item.get("gtin")

        if gtin and not _validate_gtin(str(gtin)):
            issues.append(
                Issue(
                    rule_id="ITM-05",
                    severity=Severity.WARN,
                    message=f"Riga {i + 1}: GTIN '{gtin}' ha checksum non valido",
                    json_pointer=f"/lines/{i}/item/gtin",
                    suggestion="Verificare il codice GTIN",
                )
            )

    return issues


def _validate_gtin(gtin: str) -> bool:
    """Validate GTIN checksum (works for GTIN-8, GTIN-12, GTIN-13, GTIN-14)."""
    digits = "".join(c for c in gtin if c.isdigit())
    if len(digits) not in (8, 12, 13, 14):
        return False

    digits = digits.zfill(14)
    total = 0
    for i, digit in enumerate(digits[:-1]):
        weight = 3 if i % 2 == 0 else 1
        total += int(digit) * weight

    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(digits[-1])


@rule("ITM-06", Severity.WARN)
def itm_06_duplicate_lines(ctx: RuleContext) -> list[Issue]:
    """Segnala righe duplicate nello stesso ordine."""
    lines = ctx.order.get("lines", [])
    seen: dict[str, int] = {}
    issues = []

    for i, line in enumerate(lines):
        item = line.get("item", {})
        item_id = item.get("id") or item.get("item_id") or item.get("description", "")

        if item_id in seen:
            issues.append(
                Issue(
                    rule_id="ITM-06",
                    severity=Severity.WARN,
                    message=f"Riga {i + 1}: articolo '{item_id}' duplicato (già in riga {seen[item_id] + 1})",
                    json_pointer=f"/lines/{i}",
                    suggestion="Consolidare le righe o verificare se corretto",
                )
            )
        else:
            seen[item_id] = i

    return issues


@rule("ITM-07", Severity.REVIEW)
def itm_07_customer_xref_candidate(ctx: RuleContext) -> list[Issue]:
    """Segnala xref cliente con status CANDIDATE."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        xref = line.get("customer_item_xref", {})
        if xref.get("status") == "CANDIDATE":
            issues.append(
                Issue(
                    rule_id="ITM-07",
                    severity=Severity.REVIEW,
                    message=f"Riga {i + 1}: xref cliente in stato CANDIDATE",
                    json_pointer=f"/lines/{i}/customer_item_xref",
                    suggestion="Confermare o rifiutare l'associazione xref",
                    details={
                        "customer_code": xref.get("customer_code"),
                        "item_id": xref.get("item_id"),
                    },
                )
            )

    return issues
