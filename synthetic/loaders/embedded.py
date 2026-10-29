"""Loader che genera i dati master inline (fallback)."""

from pathlib import Path
from typing import Any

from ..catalog import generate_catalog
from ..customers import generate_customers


class EmbeddedLoader:
    """Loader che usa i generatori embedded.

    Questo loader genera i dati master usando le funzioni in catalog.py e
    customers.py. È il fallback quando datagen/master/ non è disponibile.
    """

    def load_catalog(self, output_path: Path | None = None) -> list[dict[str, Any]]:
        """Genera il catalogo articoli inline."""
        return generate_catalog(output_path)

    def load_customers(
        self,
        catalog: list[dict[str, Any]],
        output_path: Path | None = None
    ) -> list[dict[str, Any]]:
        """Genera i clienti con xref inline."""
        return generate_customers(catalog, output_path)
