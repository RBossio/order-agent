"""Controlli incrociati post-estrazione: importi, totali, anagrafica, date."""

from __future__ import annotations

from datetime import date

from .catalog import CatalogMatcher
from .confidence import drop_below_review
from .dates import parse_date_obj
from .models import (
    ExtractedOrder,
    ExtractionWarning,
    FieldConfidence,
    WarningSeverity,
)

_AMOUNT_ABS_TOL = 0.05
_AMOUNT_PCT_TOL = 0.005
_DATE_YEAR_MIN = 2025
_DATE_YEAR_MAX = 2027


def apply_cross_checks(
    order: ExtractedOrder,
    catalog: CatalogMatcher,
    field_confidences: list[FieldConfidence],
    warnings: list[ExtractionWarning],
    *,
    as_of: date | None = None,
) -> None:
    """Esegue i controlli e abbassa la confidenza sotto soglia se falliscono."""
    _check_line_amounts(order, field_confidences, warnings)
    _check_totals(order, field_confidences, warnings)
    _check_catalog(order, catalog, field_confidences, warnings)
    _check_dates(order, field_confidences, warnings, as_of=as_of)


def _check_line_amounts(
    order: ExtractedOrder,
    field_confidences: list[FieldConfidence],
    warnings: list[ExtractionWarning],
) -> None:
    for index, line in enumerate(order.lines):
        if line.quantity is None or line.unit_price is None or line.line_amount is None:
            continue
        expected = line.quantity * line.unit_price
        allowed = max(_AMOUNT_ABS_TOL, abs(expected) * _AMOUNT_PCT_TOL)
        if abs(line.line_amount - expected) <= allowed:
            continue
        path = f"/lines/{index}/line_amount"
        warnings.append(ExtractionWarning(
            code="PRC-03",
            severity=WarningSeverity.REVIEW,
            message=(
                f"Riga {line.line_no}: importo {line.line_amount:.2f} "
                f"≠ {line.quantity:g} × {line.unit_price:.2f}"
            ),
            path=path,
        ))
        drop_below_review(field_confidences, path)
        drop_below_review(field_confidences, f"/lines/{index}/quantity")
        drop_below_review(field_confidences, f"/lines/{index}/unit_price")


def _check_totals(
    order: ExtractedOrder,
    field_confidences: list[FieldConfidence],
    warnings: list[ExtractionWarning],
) -> None:
    if order.totals is None:
        return
    declared = order.totals.total_amount_declared or order.totals.lines_amount_declared
    if declared is None:
        return
    computed = 0.0
    for line in order.lines:
        if line.line_amount is not None:
            computed += line.line_amount
        elif line.quantity is not None and line.unit_price is not None:
            computed += line.quantity * line.unit_price
    allowed = max(0.02, abs(declared) * 0.001)
    if abs(declared - computed) <= allowed:
        return
    warnings.append(ExtractionWarning(
        code="TOT-01",
        severity=WarningSeverity.REVIEW,
        message=f"Totale dichiarato {declared:.2f} ≠ somma righe {computed:.2f}",
        path="/totals/total_amount_declared",
    ))
    drop_below_review(field_confidences, "/totals/total_amount_declared")
    for index in range(len(order.lines)):
        drop_below_review(field_confidences, f"/lines/{index}/quantity")
        drop_below_review(field_confidences, f"/lines/{index}/unit_price")


def _check_catalog(
    order: ExtractedOrder,
    catalog: CatalogMatcher,
    field_confidences: list[FieldConfidence],
    warnings: list[ExtractionWarning],
) -> None:
    for index, line in enumerate(order.lines):
        in_catalog = catalog.item_in_catalog(line.seller_item_code, line.buyer_item_code)
        if not in_catalog and (line.seller_item_code or line.buyer_item_code):
            path = f"/lines/{index}/seller_item_code"
            warnings.append(ExtractionWarning(
                code="ITM-01",
                severity=WarningSeverity.REVIEW,
                message=(
                    f"Riga {line.line_no}: articolo "
                    f"'{line.seller_item_code or line.buyer_item_code}' non in anagrafica"
                ),
                path=path,
            ))
            drop_below_review(field_confidences, path)
            drop_below_review(field_confidences, f"/lines/{index}/buyer_item_code")

        raw = line.uom or line.uom_raw
        if raw and not catalog.is_valid_uom(raw):
            path = f"/lines/{index}/uom"
            warnings.append(ExtractionWarning(
                code="UOM-01",
                severity=WarningSeverity.REVIEW,
                message=f"Riga {line.line_no}: UoM '{raw}' non riconosciuta",
                path=path,
            ))
            drop_below_review(field_confidences, path)
            drop_below_review(field_confidences, f"/lines/{index}/uom_raw")


def _check_dates(
    order: ExtractedOrder,
    field_confidences: list[FieldConfidence],
    warnings: list[ExtractionWarning],
    *,
    as_of: date | None = None,
) -> None:
    if order.header is None:
        return
    po_date = parse_date_obj(order.header.po_date)
    if order.header.po_date and po_date is None:
        warnings.append(ExtractionWarning(
            code="HDR-02",
            severity=WarningSeverity.REVIEW,
            message=f"Data ordine non parsabile: {order.header.po_date!r}",
            path="/header/po_date",
        ))
        drop_below_review(field_confidences, "/header/po_date")
    elif po_date is not None and not _year_plausible(po_date):
        warnings.append(ExtractionWarning(
            code="HDR-02",
            severity=WarningSeverity.REVIEW,
            message=f"Data ordine non plausibile: {po_date.isoformat()}",
            path="/header/po_date",
        ))
        drop_below_review(field_confidences, "/header/po_date")

    delivery = parse_date_obj(order.header.requested_delivery_date)
    if order.header.requested_delivery_date and delivery is None:
        warnings.append(ExtractionWarning(
            code="HDR-04",
            severity=WarningSeverity.REVIEW,
            message=f"Data consegna non parsabile: {order.header.requested_delivery_date!r}",
            path="/header/requested_delivery_date",
        ))
        drop_below_review(field_confidences, "/header/requested_delivery_date")
    elif delivery is not None:
        if not _year_plausible(delivery):
            warnings.append(ExtractionWarning(
                code="HDR-04",
                severity=WarningSeverity.REVIEW,
                message=f"Data consegna non plausibile: {delivery.isoformat()}",
                path="/header/requested_delivery_date",
            ))
            drop_below_review(field_confidences, "/header/requested_delivery_date")
        elif po_date is not None and delivery < po_date:
            warnings.append(ExtractionWarning(
                code="HDR-04",
                severity=WarningSeverity.REVIEW,
                message="Data di consegna precedente alla data PO",
                path="/header/requested_delivery_date",
            ))
            drop_below_review(field_confidences, "/header/requested_delivery_date")
        elif as_of is not None and delivery < as_of:
            warnings.append(ExtractionWarning(
                code="HDR-04",
                severity=WarningSeverity.REVIEW,
                message=f"Data di consegna {delivery.isoformat()} già passata",
                path="/header/requested_delivery_date",
            ))
            drop_below_review(field_confidences, "/header/requested_delivery_date")


def _year_plausible(value: date) -> bool:
    return _DATE_YEAR_MIN <= value.year <= _DATE_YEAR_MAX
