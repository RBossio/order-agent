"""PRC: Price validation rules."""

from rules.models import Issue, RuleContext, Severity
from rules.registry import rule


@rule("PRC-01", Severity.REVIEW)
def prc_01_price_tolerance(ctx: RuleContext) -> list[Issue]:
    """Verifica che il prezzo sia entro la tolleranza rispetto al listino."""
    lines = ctx.order.get("lines", [])
    ref = ctx.reference_data
    tolerance_pct = ctx.thresholds.get("price_tolerance_pct", 2.0)
    issues = []

    for i, line in enumerate(lines):
        line_price = line.get("unit_price") or line.get("price")
        item = line.get("item", {})
        item_id = item.get("id") or item.get("item_id")
        customer = ctx.order.get("customer", {})
        customer_id = customer.get("id") or customer.get("customer_id")

        if line_price is not None and item_id and ref:
            expected_price = ref.get_item_price(item_id, customer_id)

            if expected_price is not None and expected_price > 0:
                diff = abs(line_price - expected_price)
                diff_pct = (diff / expected_price) * 100

                if diff_pct > tolerance_pct:
                    issues.append(
                        Issue(
                            rule_id="PRC-01",
                            severity=Severity.REVIEW,
                            message=f"Riga {i + 1}: prezzo {line_price:.2f} fuori tolleranza ({diff_pct:.1f}% vs listino {expected_price:.2f})",
                            json_pointer=f"/lines/{i}/unit_price",
                            suggestion="Verificare il prezzo con il cliente",
                            details={
                                "line_price": line_price,
                                "expected_price": expected_price,
                                "difference_pct": diff_pct,
                            },
                        )
                    )

    return issues


@rule("PRC-02", Severity.WARN)
def prc_02_missing_price(ctx: RuleContext) -> list[Issue]:
    """Segnala righe senza prezzo."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        price = line.get("unit_price") or line.get("price")

        if price is None:
            issues.append(
                Issue(
                    rule_id="PRC-02",
                    severity=Severity.WARN,
                    message=f"Riga {i + 1}: prezzo unitario mancante",
                    json_pointer=f"/lines/{i}/unit_price",
                    suggestion="Inserire il prezzo unitario",
                )
            )
        elif price <= 0:
            issues.append(
                Issue(
                    rule_id="PRC-02",
                    severity=Severity.WARN,
                    message=f"Riga {i + 1}: prezzo unitario non valido ({price})",
                    json_pointer=f"/lines/{i}/unit_price",
                    suggestion="Il prezzo deve essere positivo",
                )
            )

    return issues


@rule("PRC-03", Severity.WARN)
def prc_03_line_amount_mismatch(ctx: RuleContext) -> list[Issue]:
    """Verifica che l'importo riga corrisponda a qty x prezzo."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        qty = line.get("quantity")
        price = line.get("unit_price") or line.get("price")
        amount = line.get("line_amount") or line.get("amount")

        if qty is not None and price is not None and amount is not None:
            expected = qty * price
            if abs(amount - expected) > 0.01:
                issues.append(
                    Issue(
                        rule_id="PRC-03",
                        severity=Severity.WARN,
                        message=f"Riga {i + 1}: importo {amount:.2f} non corrisponde a {qty} x {price:.2f} = {expected:.2f}",
                        json_pointer=f"/lines/{i}/line_amount",
                        suggestion="Verificare l'importo della riga",
                        details={
                            "quantity": qty,
                            "price": price,
                            "line_amount": amount,
                            "expected": expected,
                        },
                    )
                )

    return issues


@rule("PRC-04", Severity.INFO)
def prc_04_ambiguous_price_basis(ctx: RuleContext) -> list[Issue]:
    """Segnala quando non è chiaro se il prezzo è unitario o totale."""
    lines = ctx.order.get("lines", [])
    issues = []

    for i, line in enumerate(lines):
        price_basis = line.get("price_basis")
        if price_basis and price_basis.lower() in ("unknown", "ambiguous"):
            issues.append(
                Issue(
                    rule_id="PRC-04",
                    severity=Severity.INFO,
                    message=f"Riga {i + 1}: base prezzo ambigua",
                    json_pointer=f"/lines/{i}/price_basis",
                    suggestion="Chiarire se il prezzo è unitario o per l'intera riga",
                )
            )

    return issues
