"""
Loader per i dati master (catalogo, clienti, cross-reference).

Questo modulo fornisce un'interfaccia astratta per caricare i dati master,
permettendo di sostituire facilmente la fonte dei dati senza modificare
il generatore degli ordini.

Fonti supportate:
- `embedded`: Dati generati inline (catalog.py, customers.py)
- `datagen`: Dati da datagen/master/ (quando disponibile)

Uso:
    from synthetic.loaders import get_loader
    
    loader = get_loader()  # Sceglie automaticamente la fonte disponibile
    catalog = loader.load_catalog()
    customers = loader.load_customers(catalog)
"""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MasterDataLoader(Protocol):
    """Interfaccia per il caricamento dei dati master.
    
    Implementazioni:
    - EmbeddedLoader: genera i dati inline (fallback)
    - DatagenLoader: carica da datagen/master/ (preferito quando disponibile)
    """
    
    def load_catalog(self, output_path: Path | None = None) -> list[dict[str, Any]]:
        """Carica il catalogo articoli (300 SKU MRO/JanSan).
        
        Args:
            output_path: Se specificato, salva il catalogo in JSON.
            
        Returns:
            Lista di articoli con: sku, description, uom, pack, price, erp_product_id, category
        """
        ...
    
    def load_customers(
        self, 
        catalog: list[dict[str, Any]], 
        output_path: Path | None = None
    ) -> list[dict[str, Any]]:
        """Carica i clienti con cross-reference.
        
        Args:
            catalog: Catalogo articoli per generare/validare xref.
            output_path: Se specificato, salva i clienti in JSON.
            
        Returns:
            Lista di clienti con: customer_id, name, order_style, xref, ship_to, ...
        """
        ...


def get_loader(prefer_datagen: bool = True) -> MasterDataLoader:
    """Ottiene il loader appropriato per i dati master.
    
    Args:
        prefer_datagen: Se True, usa datagen/master/ quando disponibile.
        
    Returns:
        Istanza di MasterDataLoader.
    """
    if prefer_datagen:
        datagen_path = Path(__file__).parent.parent.parent / "datagen" / "master"
        if datagen_path.exists():
            from .datagen import DatagenLoader
            return DatagenLoader(datagen_path)
    
    from .embedded import EmbeddedLoader
    return EmbeddedLoader()


__all__ = ["MasterDataLoader", "get_loader"]
