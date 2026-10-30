"""Pipeline demo: ingest → estrazione deterministica → (match se c'è) → regole.

Non usa il ground truth, non inventa confidenze, allowlist o clienti.
``ventureorder.match`` su main è ancora vuoto: buyer/righe restano non riconosciuti.
"""

from __future__ import annotations

import copy
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from ventureorder.rules import DatagenReferenceDataProvider, HistoricalOrder, ValidationEngine

DEMO_AS_OF = date(2026, 4, 2)

DEMO_STEMS = (
    "order_001_TIT-PO-01000",
    "order_002_QS-01001",
    "order_003_MBM01002",
    "order_004_TIT-PO-01003",
    "order_005_MBM01004",
    "order_006_BW-01005",
    "order_012_QS-01011",
    "order_027_NMC-01026",
    "order_028_SW-01027",
)


def repo_root() -> Path:
    """Radice del repo (synthetic/ e ingest/), cercata da CWD e dal file."""
    here = Path(__file__).resolve()
    for candidate in (Path.cwd(), *here.parents):
        if (candidate / "synthetic" / "documents").is_dir() and (
            candidate / "datagen" / "master" / "products.json"
        ).is_file():
            return candidate
    return Path.cwd()


def _ensure_repo_on_path() -> Path:
    root = repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def find_document(stem: str) -> Path | None:
    """Percorso del documento sintetico per uno stem ``order_NNN_PO``."""
    documents = repo_root() / "synthetic" / "documents"
    for folder, suffix in (("xlsx", ".xlsx"), ("eml", ".eml"), ("pdf", ".pdf")):
        path = documents / folder / f"{stem}{suffix}"
        if path.is_file():
            return path
    return None


def build_reference_provider() -> DatagenReferenceDataProvider:
    """Anagrafica datagen così com'è (nessuna allowlist artificiale)."""
    return DatagenReferenceDataProvider.from_datagen()


def build_engine(provider: DatagenReferenceDataProvider) -> ValidationEngine:
    """Motore regole ancorato alla data demo ``2026-04-02``."""
    return ValidationEngine(reference_data=provider, as_of=DEMO_AS_OF)


def ingest_and_extract(path: Path) -> dict[str, Any] | None:
    """Ingest + estrazione deterministica (MockBackend). ``None`` se fallisce."""
    import importlib

    _ensure_repo_on_path()
    ingest_mod = importlib.import_module("ingest")
    extract_mod = importlib.import_module("extract")
    backends_mod = importlib.import_module("extract.backends")
    try:
        normalized = ingest_mod.Ingestor().ingest(path)
        catalog_mod = importlib.import_module("extract.catalog")
        result = extract_mod.OrderExtractor(
            backend=backends_mod.MockBackend(),
            validate_output=False,
            catalog=catalog_mod.CatalogMatcher(allowlist_synthetic=False),
        ).extract(normalized.to_dict())
    except Exception:  # noqa: BLE001 — un documento non deve far cadere la demo
        return None
    payload = result.to_dict()
    return payload if isinstance(payload, dict) else None


def apply_match_if_available(
    vof: dict[str, Any], provider: DatagenReferenceDataProvider
) -> dict[str, Any]:
    """Applica ``ventureorder.match`` solo se il modulo esiste ed espone un resolver.

    Su main il pacchetto è vuoto: il VOF resta senza ``buyer.resolved`` / ``resolution``.
    """
    import importlib
    import importlib.util

    spec = importlib.util.find_spec("ventureorder.match")
    if spec is None:
        return vof
    try:
        module = importlib.import_module("ventureorder.match")
    except Exception:  # noqa: BLE001
        return vof
    for name in ("resolve_order", "match_order", "apply"):
        func = getattr(module, name, None)
        if callable(func):
            matched = func(vof, provider)
            return matched if isinstance(matched, dict) else vof
    return vof


def load_extracted_vof(
    stem: str, provider: DatagenReferenceDataProvider
) -> dict[str, Any] | None:
    """VOF reale da ingest → extract → match opzionale. Nessun ground truth."""
    document = find_document(stem)
    if document is None:
        return None
    extracted = ingest_and_extract(document)
    if extracted is None:
        return None
    return apply_match_if_available(extracted, provider)


def clone_vof(vof: dict[str, Any], *, order_id: str) -> dict[str, Any]:
    """Copia un VOF con nuovo ``order_id``, stessi hash (per DUP-02)."""
    clone = copy.deepcopy(vof)
    clone["order_id"] = order_id
    return clone


def historical_from_vof(vof: dict[str, Any]) -> HistoricalOrder:
    """Ordine già visto, per far scattare DUP-02 sul duplicato."""
    header = vof.get("header") or {}
    source = vof.get("source") or {}
    documents = source.get("documents") or []
    sha = None
    if documents and isinstance(documents[0], dict):
        sha = documents[0].get("sha256")
    resolved = (vof.get("buyer") or {}).get("resolved") or {}
    customer_ref = str(resolved.get("erp_partner_ref") or "")
    return HistoricalOrder(
        order_id=str(vof.get("order_id") or uuid.uuid4()),
        customer_ref=customer_ref,
        po_number=str(header.get("po_number") or ""),
        po_revision=int(header.get("po_revision") or 0),
        po_date=str(header.get("po_date") or "") or None,
        status="POSTED",
        sha256=str(sha) if sha else None,
        message_id=source.get("message_id"),
        lines=[],
    )
