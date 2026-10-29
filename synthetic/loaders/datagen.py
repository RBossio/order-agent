"""Loader che carica i dati master da datagen/master/.

Questo loader sarà usato quando l'altra PR (Odoo in Docker) introdurrà
i dati deterministici in datagen/master/.

Formato atteso (da confermare in datagen/README.md):
- datagen/master/catalog.json: 300 articoli
- datagen/master/customers.json: 10 clienti
- datagen/master/customer_item_xref.json: tabella codici cliente
"""

import json
from pathlib import Path
from typing import Any


class DatagenLoader:
    """Loader che carica da datagen/master/.
    
    Prerequisito: i file devono esistere con il formato specificato
    in datagen/README.md.
    """
    
    def __init__(self, datagen_path: Path):
        """Inizializza il loader.
        
        Args:
            datagen_path: Percorso a datagen/master/
        """
        self.datagen_path = datagen_path
        self._validate_path()
    
    def _validate_path(self) -> None:
        """Verifica che i file necessari esistano."""
        required_files = ["catalog.json", "customers.json"]
        for fname in required_files:
            fpath = self.datagen_path / fname
            if not fpath.exists():
                raise FileNotFoundError(
                    f"File {fpath} non trovato. "
                    f"Assicurati che datagen/master/ contenga i dati master."
                )
    
    def load_catalog(self, output_path: Path | None = None) -> list[dict[str, Any]]:
        """Carica il catalogo da datagen/master/catalog.json.
        
        Args:
            output_path: Se specificato, copia il catalogo in questa posizione.
            
        Returns:
            Lista di articoli.
        """
        catalog_path = self.datagen_path / "catalog.json"
        with open(catalog_path, encoding="utf-8") as f:
            catalog = json.load(f)
        
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(catalog, f, indent=2, ensure_ascii=False)
        
        return catalog
    
    def load_customers(
        self, 
        catalog: list[dict[str, Any]], 
        output_path: Path | None = None
    ) -> list[dict[str, Any]]:
        """Carica i clienti da datagen/master/customers.json.
        
        Se esiste customer_item_xref.json, integra i codici cliente.
        
        Args:
            catalog: Catalogo articoli (usato per validare xref).
            output_path: Se specificato, salva i clienti in questa posizione.
            
        Returns:
            Lista di clienti con xref integrato.
        """
        customers_path = self.datagen_path / "customers.json"
        with open(customers_path, encoding="utf-8") as f:
            customers = json.load(f)
        
        xref_path = self.datagen_path / "customer_item_xref.json"
        if xref_path.exists():
            with open(xref_path, encoding="utf-8") as f:
                xref_data = json.load(f)
            
            sku_to_item = {item["sku"]: item for item in catalog}
            
            for customer in customers:
                customer_id = customer["customer_id"]
                customer_xrefs = [
                    x for x in xref_data 
                    if x.get("customer_id") == customer_id
                ]
                
                validated_xrefs = []
                for xref in customer_xrefs:
                    sku = xref.get("sku")
                    if sku in sku_to_item:
                        validated_xrefs.append({
                            "customer_code": xref["customer_code"],
                            "sku": sku,
                            "erp_product_id": sku_to_item[sku].get("erp_product_id"),
                            "status": xref.get("status", "TRUSTED")
                        })
                
                customer["xref"] = validated_xrefs
        
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(customers, f, indent=2, ensure_ascii=False)
        
        return customers
