"""Loader embedded per fallback test - DEPRECATO.

Questo loader genera dati master minimi inline ed è mantenuto solo
come fallback esplicito per test quando datagen/master/ non è disponibile.

Per uso normale, usare DatagenLoader con datagen/master/.
"""

import warnings
from pathlib import Path
from typing import Any

from ..catalog import generate_catalog
from ..customers import generate_customers


class EmbeddedLoader:
    """Loader di fallback che genera dati minimi inline.
    
    DEPRECATO: Usare DatagenLoader con datagen/master/ per dati completi.
    
    Questo loader genera dati master minimi usando le funzioni in catalog.py
    e customers.py. È il fallback quando datagen/master/ non è disponibile,
    ma produce dati semplificati non adatti per test realistici.
    """
    
    def __init__(self) -> None:
        """Inizializza con warning di deprecazione."""
        warnings.warn(
            "EmbeddedLoader è deprecato. Usare DatagenLoader con datagen/master/.",
            DeprecationWarning,
            stacklevel=2
        )
    
    def load_catalog(self, output_path: Path | None = None) -> list[dict[str, Any]]:
        """Genera il catalogo articoli inline (dati semplificati)."""
        return generate_catalog(output_path)
    
    def load_customers(
        self, 
        catalog: list[dict[str, Any]], 
        output_path: Path | None = None
    ) -> list[dict[str, Any]]:
        """Genera i clienti con xref inline (dati semplificati)."""
        return generate_customers(catalog, output_path)
