"""Generatore catalogo 300 articoli MRO/JanSan."""

import json
import random
from pathlib import Path
from typing import Any

from . import SEED


def generate_catalog(output_path: Path | None = None) -> list[dict[str, Any]]:
    """Genera un catalogo di 300 articoli MRO/JanSan realistici.
    
    Args:
        output_path: Percorso opzionale per salvare il JSON.
        
    Returns:
        Lista di articoli con sku, description, uom, pack, price, erp_product_id.
    """
    random.seed(SEED)
    
    catalog: list[dict[str, Any]] = []
    erp_id = 1000
    
    # === FASTENERS (60 articoli) ===
    fastener_types = [
        ("HCS", "Hex Cap Screw", "Grade 5 Zinc"),
        ("HCS", "Hex Cap Screw", "Grade 8 Yellow Zinc"),
        ("HCS", "Hex Cap Screw", "Stainless 18-8"),
        ("SHCS", "Socket Head Cap Screw", "Alloy Steel Black Oxide"),
        ("FHCS", "Flat Head Cap Screw", "Stainless 18-8"),
        ("BHCS", "Button Head Cap Screw", "Stainless 18-8"),
        ("HN", "Hex Nut", "Grade 5 Zinc"),
        ("HN", "Hex Nut", "Stainless 18-8"),
        ("LN", "Lock Nut", "Nylon Insert Zinc"),
        ("FW", "Flat Washer", "Zinc"),
        ("LW", "Lock Washer", "Zinc"),
        ("CS", "Carriage Bolt", "Grade 5 Zinc"),
    ]
    thread_sizes = [
        ("1/4-20", "1/4-20"),
        ("5/16-18", "5/16-18"),
        ("3/8-16", "3/8-16"),
        ("1/2-13", "1/2-13"),
        ("M8-1.25", "M8x1.25"),
        ("M10-1.5", "M10x1.5"),
    ]
    lengths = ["1", "1-1/2", "2", "3"]
    pack_sizes_fastener = [25, 50, 100]
    
    for ftype, fname, fmat in fastener_types[:5]:
        for tsize, tdisp in thread_sizes[:4]:
            for length in lengths[:2]:
                pack = random.choice(pack_sizes_fastener)
                sku = f"FST-{ftype}-{tsize.replace('/', '').replace('-', '')}-{length.replace('-', '').replace('/', '')}-{'G5Z' if 'Grade 5' in fmat else 'G8' if 'Grade 8' in fmat else 'SS'}-B{pack}"
                desc = f"{fname} {tsize} x {length}\" {fmat}"
                price = round(random.uniform(8.50, 45.00), 2)
                catalog.append({
                    "sku": sku,
                    "description": desc,
                    "uom": "BX",
                    "pack": {"raw": f"{pack}/BX", "inner_count": pack, "inner_size": 1, "inner_uom": "EA"},
                    "price": price,
                    "erp_product_id": erp_id,
                    "category": "FASTENERS"
                })
                erp_id += 1
                if len(catalog) >= 60:
                    break
            if len(catalog) >= 60:
                break
        if len(catalog) >= 60:
            break
    
    while len(catalog) < 60:
        ftype, fname, fmat = random.choice(fastener_types[5:])
        tsize, tdisp = random.choice(thread_sizes)
        pack = random.choice(pack_sizes_fastener)
        sku = f"FST-{ftype}-{tsize.replace('/', '').replace('-', '')}-{'ZN' if 'Zinc' in fmat else 'SS'}-B{pack}"
        if any(c["sku"] == sku for c in catalog):
            continue
        desc = f"{fname} {tsize} {fmat}"
        price = round(random.uniform(5.00, 25.00), 2)
        catalog.append({
            "sku": sku,
            "description": desc,
            "uom": "BX",
            "pack": {"raw": f"{pack}/BX", "inner_count": pack, "inner_size": 1, "inner_uom": "EA"},
            "price": price,
            "erp_product_id": erp_id,
            "category": "FASTENERS"
        })
        erp_id += 1
    
    # === PPE / SAFETY (50 articoli) ===
    glove_types = [
        ("NIT", "Nitrile Exam Gloves", "powder-free", ["S", "M", "L", "XL"], ["Blue", "Black"]),
        ("LAT", "Latex Exam Gloves", "powder-free", ["S", "M", "L", "XL"], ["Natural"]),
        ("VIN", "Vinyl Exam Gloves", "powder-free", ["S", "M", "L", "XL"], ["Clear"]),
        ("NITW", "Nitrile Work Gloves", "industrial", ["M", "L", "XL"], ["Orange", "Black"]),
        ("LTHW", "Leather Work Gloves", "premium grain", ["M", "L", "XL"], ["Tan"]),
    ]
    glove_mils = [4, 5, 6, 8]
    
    for gtype, gname, gattr, sizes, colors in glove_types:
        for size in sizes:
            for color in colors:
                mil = random.choice(glove_mils) if "Exam" in gname else None
                mil_str = f" {mil} mil" if mil else ""
                sku = f"PPE-GLV-{gtype}{mil or ''}-{size}-{color[:3].upper()}"
                desc = f"{gname}{mil_str} {gattr} {color} size {size}"
                if "Exam" in gname:
                    pack = {"raw": "100/BX 10BX/CS", "inner_count": 1000, "inner_size": 1, "inner_uom": "EA"}
                    uom = "CS"
                    price = round(random.uniform(75.00, 120.00), 2)
                else:
                    pack = {"raw": "12/DZ", "inner_count": 12, "inner_size": 1, "inner_uom": "PR"}
                    uom = "DZN"
                    price = round(random.uniform(25.00, 85.00), 2)
                catalog.append({
                    "sku": sku,
                    "description": desc,
                    "uom": uom,
                    "pack": pack,
                    "price": price,
                    "erp_product_id": erp_id,
                    "category": "PPE"
                })
                erp_id += 1
                if len(catalog) >= 90:
                    break
            if len(catalog) >= 90:
                break
        if len(catalog) >= 90:
            break
    
    safety_items = [
        ("PPE-GLS-AF-CLR", "Safety Glasses clear lens anti-fog ANSI Z87.1", "EA", None, 3.25),
        ("PPE-GLS-AF-AMB", "Safety Glasses amber lens anti-fog ANSI Z87.1", "EA", None, 3.45),
        ("PPE-GLS-AF-SMK", "Safety Glasses smoke lens anti-fog ANSI Z87.1", "EA", None, 3.45),
        ("PPE-GGL-CLR", "Safety Goggles indirect vent clear lens", "EA", None, 5.75),
        ("PPE-GGL-OTG", "Safety Goggles over-the-glasses clear", "EA", None, 7.25),
        ("PPE-FSH-CLR", "Face Shield clear 8x15.5 inch", "EA", None, 4.50),
        ("PPE-HH-WHT", "Hard Hat Type I Class E white", "EA", None, 12.50),
        ("PPE-HH-YEL", "Hard Hat Type I Class E yellow", "EA", None, 12.50),
        ("PPE-HH-BLU", "Hard Hat Type I Class E blue", "EA", None, 12.50),
        ("PPE-EP-FOAM", "Ear Plugs foam disposable NRR 32", "BX", {"raw": "200/BX", "inner_count": 200, "inner_size": 1, "inner_uom": "PR"}, 18.75),
        ("PPE-EP-CORD", "Ear Plugs foam corded NRR 32", "BX", {"raw": "100/BX", "inner_count": 100, "inner_size": 1, "inner_uom": "PR"}, 22.50),
        ("PPE-EM-ADJ", "Ear Muffs adjustable NRR 25", "EA", None, 14.25),
        ("PPE-RESP-N95", "N95 Respirator NIOSH approved", "BX", {"raw": "20/BX", "inner_count": 20, "inner_size": 1, "inner_uom": "EA"}, 28.50),
        ("PPE-RESP-N95V", "N95 Respirator with valve NIOSH approved", "BX", {"raw": "10/BX", "inner_count": 10, "inner_size": 1, "inner_uom": "EA"}, 32.00),
        ("PPE-VEST-HV-OR", "Hi-Vis Safety Vest Class 2 orange", "EA", None, 8.50),
        ("PPE-VEST-HV-LM", "Hi-Vis Safety Vest Class 2 lime", "EA", None, 8.50),
    ]
    
    for sku, desc, uom, pack, price in safety_items:
        catalog.append({
            "sku": sku,
            "description": desc,
            "uom": uom,
            "pack": pack,
            "price": price,
            "erp_product_id": erp_id,
            "category": "PPE"
        })
        erp_id += 1
    
    while len(catalog) < 110:
        catalog.append({
            "sku": f"PPE-MISC-{erp_id}",
            "description": f"Safety equipment item {erp_id}",
            "uom": "EA",
            "pack": None,
            "price": round(random.uniform(5.00, 50.00), 2),
            "erp_product_id": erp_id,
            "category": "PPE"
        })
        erp_id += 1
    
    # === JANSAN LINERS (40 articoli) ===
    liner_sizes = [
        ("24x24", "10 gal"),
        ("24x32", "12-16 gal"),
        ("30x37", "20-30 gal"),
        ("33x40", "33 gal"),
        ("40x46", "40-45 gal"),
        ("40x48", "45 gal"),
        ("43x47", "56 gal"),
    ]
    liner_mils = ["0.5", "0.7", "1.0", "1.2", "1.5", "2.0"]
    liner_colors = ["Clear", "Black", "White"]
    liner_counts = [100, 150, 200, 250, 500]
    
    for size, gal in liner_sizes:
        for mil in liner_mils[:3]:
            for color in liner_colors[:2]:
                count = random.choice(liner_counts)
                sku = f"JAN-LNR-{size.replace('x', '')}-{mil.replace('.', '')}-{color[:2].upper()}"
                if any(c["sku"] == sku for c in catalog):
                    continue
                desc = f"Can Liner {size} {mil}mil {color} {count}/CS"
                price = round(random.uniform(25.00, 65.00), 2)
                catalog.append({
                    "sku": sku,
                    "description": desc,
                    "uom": "CS",
                    "pack": {"raw": f"{count}/CS", "inner_count": count, "inner_size": 1, "inner_uom": "EA"},
                    "price": price,
                    "erp_product_id": erp_id,
                    "category": "JANSAN_LINERS"
                })
                erp_id += 1
                if len(catalog) >= 150:
                    break
            if len(catalog) >= 150:
                break
        if len(catalog) >= 150:
            break
    
    # === JANSAN CHEMICALS (50 articoli) ===
    chemicals = [
        ("NFC", "Neutral Floor Cleaner", "concentrate", "4/1 GAL", 4, 1, "GLL", 48.00),
        ("NFC-RTU", "Neutral Floor Cleaner", "ready to use", "4/1 GAL", 4, 1, "GLL", 32.00),
        ("GPC", "General Purpose Cleaner", "concentrate", "4/1 GAL", 4, 1, "GLL", 42.00),
        ("GPC-RTU", "General Purpose Cleaner", "ready to use", "6/32 OZ", 6, 32, "OZA", 28.00),
        ("GLS-CLN", "Glass Cleaner", "ready to use", "6/32 OZ", 6, 32, "OZA", 24.00),
        ("GLS-CLN-GAL", "Glass Cleaner", "concentrate", "4/1 GAL", 4, 1, "GLL", 38.00),
        ("DEGS", "Degreaser Heavy Duty", "concentrate", "4/1 GAL", 4, 1, "GLL", 52.00),
        ("DEGS-RTU", "Degreaser Heavy Duty", "ready to use", "6/32 OZ", 6, 32, "OZA", 32.00),
        ("DISF-QT", "Disinfectant Quaternary", "concentrate", "4/1 GAL", 4, 1, "GLL", 58.00),
        ("DISF-QT-RTU", "Disinfectant Quaternary", "ready to use", "6/32 OZ", 6, 32, "OZA", 36.00),
        ("DISF-BLC", "Disinfectant Bleach", "concentrate", "6/1 GAL", 6, 1, "GLL", 42.00),
        ("SS-CLN", "Stainless Steel Cleaner", "ready to use", "6/32 OZ", 6, 32, "OZA", 38.00),
        ("BATH-CLN", "Bathroom Cleaner", "concentrate", "4/1 GAL", 4, 1, "GLL", 44.00),
        ("BATH-CLN-RTU", "Bathroom Cleaner", "ready to use", "6/32 OZ", 6, 32, "OZA", 26.00),
        ("CRPT-CLN", "Carpet Cleaner", "concentrate", "4/1 GAL", 4, 1, "GLL", 56.00),
        ("CRPT-SPOT", "Carpet Spot Remover", "ready to use", "6/32 OZ", 6, 32, "OZA", 34.00),
        ("HND-SOAP", "Hand Soap Liquid", "bulk", "4/1 GAL", 4, 1, "GLL", 35.00),
        ("HND-SOAP-FM", "Hand Soap Foam", "refill", "6/1250 ML", 6, 1250, "MLT", 52.00),
        ("HND-SAN", "Hand Sanitizer Gel", "bulk", "4/1 GAL", 4, 1, "GLL", 48.00),
        ("HND-SAN-FM", "Hand Sanitizer Foam", "refill", "6/1200 ML", 6, 1200, "MLT", 58.00),
        ("AIR-FRSH", "Air Freshener", "aerosol", "12/10 OZ", 12, 10, "OZA", 36.00),
        ("ODOR-CTL", "Odor Control", "concentrate", "4/1 GAL", 4, 1, "GLL", 46.00),
        ("DRAIN-MNT", "Drain Maintainer", "concentrate", "4/1 GAL", 4, 1, "GLL", 62.00),
        ("GROUT-CLN", "Grout Cleaner", "concentrate", "4/1 GAL", 4, 1, "GLL", 54.00),
        ("FLR-FNSH", "Floor Finish High Gloss", "ready to use", "4/1 GAL", 4, 1, "GLL", 68.00),
        ("FLR-STRP", "Floor Stripper", "concentrate", "4/1 GAL", 4, 1, "GLL", 58.00),
    ]
    
    for ccode, cname, cattr, pack_raw, inner_ct, inner_sz, inner_uom, base_price in chemicals:
        sku = f"JAN-{ccode}"
        desc = f"{cname} {cattr} {pack_raw}"
        price = round(base_price * random.uniform(0.95, 1.05), 2)
        catalog.append({
            "sku": sku,
            "description": desc,
            "uom": "CS",
            "pack": {"raw": pack_raw, "inner_count": inner_ct, "inner_size": inner_sz, "inner_uom": inner_uom},
            "price": price,
            "erp_product_id": erp_id,
            "category": "JANSAN_CHEMICALS"
        })
        erp_id += 1
    
    # === PAPER PRODUCTS (30 articoli) ===
    paper_products = [
        ("TWL-MF", "Multifold Paper Towels White", "16/250/CS", 16, 250, "EA", 42.00),
        ("TWL-MF-BR", "Multifold Paper Towels Brown", "16/250/CS", 16, 250, "EA", 38.00),
        ("TWL-CF", "Centerfeed Paper Towels White", "6/600/CS", 6, 600, "EA", 48.00),
        ("TWL-CF-BR", "Centerfeed Paper Towels Brown", "6/600/CS", 6, 600, "EA", 44.00),
        ("TWL-RL", "Roll Paper Towels White 2-ply", "12/85/CS", 12, 85, "EA", 36.00),
        ("TWL-RL-BR", "Roll Paper Towels Brown 1-ply", "12/350/CS", 12, 350, "EA", 32.00),
        ("TWL-HRT", "Hardwound Roll Towels White 8x800", "6/CS", 6, 1, "RO", 58.00),
        ("TWL-HRT-BR", "Hardwound Roll Towels Brown 8x800", "6/CS", 6, 1, "RO", 52.00),
        ("TP-2P-96", "Toilet Paper 2-ply standard roll", "96/CS", 96, 1, "RO", 65.00),
        ("TP-2P-48", "Toilet Paper 2-ply standard roll", "48/CS", 48, 1, "RO", 34.00),
        ("TP-JR-12", "Toilet Paper Jumbo Roll 2-ply 9 inch", "12/CS", 12, 1, "RO", 48.00),
        ("TP-JR-6", "Toilet Paper Jumbo Roll 2-ply 9 inch", "6/CS", 6, 1, "RO", 26.00),
        ("FS-2P", "Facial Tissue 2-ply cube box", "36/100/CS", 36, 100, "EA", 42.00),
        ("FS-2P-FLAT", "Facial Tissue 2-ply flat box", "30/100/CS", 30, 100, "EA", 38.00),
        ("TC-SEAT", "Toilet Seat Covers half-fold", "20/250/CS", 20, 250, "EA", 36.00),
        ("TC-DISP", "Toilet Seat Cover Dispenser chrome", "EA", 1, 1, "EA", 12.50),
        ("DISP-TWL-MF", "Towel Dispenser Multifold chrome", "EA", 1, 1, "EA", 28.00),
        ("DISP-TWL-CF", "Towel Dispenser Centerfeed chrome", "EA", 1, 1, "EA", 35.00),
        ("DISP-TP-JR", "Toilet Paper Dispenser Jumbo chrome", "EA", 1, 1, "EA", 32.00),
        ("DISP-SOAP", "Soap Dispenser manual chrome", "EA", 1, 1, "EA", 18.00),
    ]
    
    for pcode, pdesc, pack_raw, inner_ct, inner_sz, inner_uom, base_price in paper_products:
        sku = f"JAN-{pcode}"
        uom = "EA" if inner_ct == 1 else "CS"
        pack = {"raw": pack_raw, "inner_count": inner_ct, "inner_size": inner_sz, "inner_uom": inner_uom} if inner_ct > 1 else None
        price = round(base_price * random.uniform(0.95, 1.05), 2)
        catalog.append({
            "sku": sku,
            "description": pdesc,
            "uom": uom,
            "pack": pack,
            "price": price,
            "erp_product_id": erp_id,
            "category": "JANSAN_PAPER"
        })
        erp_id += 1
    
    # === ABRASIVES (30 articoli) ===
    abrasive_grits = [40, 60, 80, 100, 120, 150, 180, 220]
    abrasive_types = [
        ("SAND-SHT", "Sandpaper Sheet 9x11", "50/PK"),
        ("SAND-DSC-5", "Sanding Disc 5 inch hook & loop", "50/PK"),
        ("SAND-DSC-6", "Sanding Disc 6 inch hook & loop", "50/PK"),
        ("FLAP-DSC-4", "Flap Disc 4.5 inch Type 27", "10/BX"),
        ("CUT-WHL-4", "Cut-off Wheel 4.5x.045x7/8", "25/BX"),
        ("CUT-WHL-6", "Cut-off Wheel 6x.045x7/8", "25/BX"),
        ("GRND-WHL-4", "Grinding Wheel 4.5x1/4x7/8", "10/BX"),
        ("WIRE-WHL", "Wire Wheel 4 inch crimped", "EA"),
    ]
    
    for atype, adesc, pack_raw in abrasive_types:
        for grit in random.sample(abrasive_grits, min(4, len(abrasive_grits))):
            sku = f"ABR-{atype}-{grit}"
            if any(c["sku"] == sku for c in catalog):
                continue
            desc = f"{adesc} {grit} grit"
            uom = pack_raw.split("/")[1] if "/" in pack_raw else "EA"
            inner_ct = int(pack_raw.split("/")[0]) if "/" in pack_raw else 1
            pack = {"raw": pack_raw, "inner_count": inner_ct, "inner_size": 1, "inner_uom": "EA"} if inner_ct > 1 else None
            price = round(random.uniform(12.00, 45.00), 2)
            catalog.append({
                "sku": sku,
                "description": desc,
                "uom": uom,
                "pack": pack,
                "price": price,
                "erp_product_id": erp_id,
                "category": "ABRASIVES"
            })
            erp_id += 1
            if len(catalog) >= 252:
                break
        if len(catalog) >= 252:
            break
    
    # === TAPES & ADHESIVES (20 articoli) ===
    tapes = [
        ("DT-2", "Duct Tape Silver 2 inch x 60 yd", "24/CS", 24, 22.00),
        ("DT-2-BK", "Duct Tape Black 2 inch x 60 yd", "24/CS", 24, 24.00),
        ("ET-3/4", "Electrical Tape Black 3/4 inch x 66 ft", "100/CS", 100, 85.00),
        ("ET-ASST", "Electrical Tape Assorted Colors", "10/PK", 10, 12.00),
        ("MT-2", "Masking Tape 2 inch x 60 yd", "24/CS", 24, 48.00),
        ("MT-1", "Masking Tape 1 inch x 60 yd", "36/CS", 36, 52.00),
        ("PT-2-CLR", "Packing Tape Clear 2 inch x 110 yd", "36/CS", 36, 68.00),
        ("PT-2-TAN", "Packing Tape Tan 2 inch x 110 yd", "36/CS", 36, 62.00),
        ("PT-GUN", "Packing Tape Gun 2 inch", "EA", 1, 8.50),
        ("STRP-TP", "Strapping Tape 3/4 inch x 60 yd", "48/CS", 48, 85.00),
        ("DBL-SIDE", "Double-Sided Tape 1 inch x 36 yd", "24/CS", 24, 72.00),
        ("FOAM-TP", "Foam Tape 1 inch x 5.5 yd", "12/CS", 12, 38.00),
        ("REFL-TP", "Reflective Tape Red/White 2 inch x 30 ft", "EA", 1, 12.50),
        ("WARN-TP-YB", "Caution Tape Yellow/Black 3 inch x 1000 ft", "12/CS", 12, 65.00),
        ("WARN-TP-RW", "Danger Tape Red/White 3 inch x 1000 ft", "12/CS", 12, 65.00),
    ]
    
    for tcode, tdesc, pack_raw, inner_ct, base_price in tapes:
        sku = f"TAP-{tcode}"
        uom = "EA" if inner_ct == 1 else "CS"
        pack = {"raw": pack_raw, "inner_count": inner_ct, "inner_size": 1, "inner_uom": "EA"} if inner_ct > 1 else None
        price = round(base_price * random.uniform(0.95, 1.05), 2)
        catalog.append({
            "sku": sku,
            "description": tdesc,
            "uom": uom,
            "pack": pack,
            "price": price,
            "erp_product_id": erp_id,
            "category": "TAPES"
        })
        erp_id += 1
    
    # === LUBRICANTS (20 articoli) ===
    lubricants = [
        ("WD40-11", "WD-40 Multi-Use 11 oz aerosol", "12/CS", 12, 48.00),
        ("WD40-GAL", "WD-40 Multi-Use 1 gallon", "4/CS", 4, 85.00),
        ("PEN-OIL", "Penetrating Oil 11 oz aerosol", "12/CS", 12, 42.00),
        ("SIL-SPR", "Silicone Spray 11 oz aerosol", "12/CS", 12, 52.00),
        ("WHT-LITH", "White Lithium Grease 14 oz cartridge", "10/BX", 10, 45.00),
        ("MOLY-GRS", "Moly Grease EP 14 oz cartridge", "10/BX", 10, 58.00),
        ("MACH-OIL", "Machine Oil Light 4 oz", "24/CS", 24, 36.00),
        ("CUT-OIL", "Cutting Oil 16 oz", "12/CS", 12, 48.00),
        ("HYD-OIL", "Hydraulic Oil AW32 5 gal pail", "EA", 1, 65.00),
        ("HYD-OIL-DR", "Hydraulic Oil AW32 55 gal drum", "EA", 1, 425.00),
        ("MTR-OIL-10W30", "Motor Oil 10W-30 1 qt", "12/CS", 12, 48.00),
        ("MTR-OIL-5W30", "Motor Oil 5W-30 1 qt", "12/CS", 12, 52.00),
        ("GEAR-OIL", "Gear Oil 80W-90 1 qt", "12/CS", 12, 58.00),
        ("CHAIN-LUB", "Chain Lubricant 11 oz aerosol", "12/CS", 12, 46.00),
        ("FOOD-GRS", "Food Grade Grease 14 oz cartridge", "10/BX", 10, 68.00),
        ("ANTI-SEIZE", "Anti-Seize Compound 8 oz", "12/CS", 12, 72.00),
        ("THRD-SEAL", "Thread Sealant PTFE 8 oz", "12/CS", 12, 48.00),
        ("LOCK-LUBE", "Lock Lubricant 3 oz", "12/CS", 12, 36.00),
    ]
    
    for lcode, ldesc, pack_raw, inner_ct, base_price in lubricants:
        sku = f"LUB-{lcode}"
        uom = "EA" if inner_ct == 1 else "CS"
        pack = {"raw": pack_raw, "inner_count": inner_ct, "inner_size": 1, "inner_uom": "EA"} if inner_ct > 1 else None
        price = round(base_price * random.uniform(0.95, 1.05), 2)
        catalog.append({
            "sku": sku,
            "description": ldesc,
            "uom": uom,
            "pack": pack,
            "price": price,
            "erp_product_id": erp_id,
            "category": "LUBRICANTS"
        })
        erp_id += 1
    
    # === FILL TO 300 ===
    misc_items = [
        ("TOOL-HMR-16", "Ball Peen Hammer 16 oz", "EA", None, 18.50),
        ("TOOL-HMR-24", "Ball Peen Hammer 24 oz", "EA", None, 22.50),
        ("TOOL-HMR-CLW", "Claw Hammer 16 oz fiberglass", "EA", None, 15.00),
        ("TOOL-SCDR-FLAT", "Screwdriver Set Flat 5pc", "EA", None, 12.00),
        ("TOOL-SCDR-PHIL", "Screwdriver Set Phillips 5pc", "EA", None, 12.00),
        ("TOOL-WRCH-ADJ", "Adjustable Wrench 10 inch", "EA", None, 14.50),
        ("TOOL-WRCH-CMB", "Combination Wrench Set SAE 14pc", "EA", None, 65.00),
        ("TOOL-WRCH-MET", "Combination Wrench Set Metric 14pc", "EA", None, 65.00),
        ("TOOL-PLIER-SLP", "Slip Joint Pliers 8 inch", "EA", None, 9.50),
        ("TOOL-PLIER-NED", "Needle Nose Pliers 6 inch", "EA", None, 11.00),
        ("TOOL-PLIER-CUT", "Diagonal Cutters 6 inch", "EA", None, 12.50),
        ("TOOL-TAP-25", "Tape Measure 25 ft", "EA", None, 8.50),
        ("TOOL-TAP-35", "Tape Measure 35 ft", "EA", None, 12.50),
        ("TOOL-LVL-24", "Level 24 inch magnetic", "EA", None, 22.00),
        ("TOOL-LVL-48", "Level 48 inch", "EA", None, 38.00),
        ("TOOL-UTIL-KNF", "Utility Knife retractable", "EA", None, 5.50),
        ("TOOL-UTIL-BLD", "Utility Knife Blades 100pk", "PK", {"raw": "100/PK", "inner_count": 100, "inner_size": 1, "inner_uom": "EA"}, 18.00),
        ("TOOL-SNIPS", "Tin Snips straight cut", "EA", None, 16.00),
        ("TOOL-PRY-12", "Pry Bar 12 inch", "EA", None, 11.00),
        ("TOOL-PRY-24", "Pry Bar 24 inch", "EA", None, 18.00),
        ("ELEC-BATT-AA", "Batteries AA Alkaline", "PK", {"raw": "24/PK", "inner_count": 24, "inner_size": 1, "inner_uom": "EA"}, 14.50),
        ("ELEC-BATT-AAA", "Batteries AAA Alkaline", "PK", {"raw": "24/PK", "inner_count": 24, "inner_size": 1, "inner_uom": "EA"}, 14.50),
        ("ELEC-BATT-9V", "Batteries 9V Alkaline", "PK", {"raw": "12/PK", "inner_count": 12, "inner_size": 1, "inner_uom": "EA"}, 22.00),
        ("ELEC-BATT-D", "Batteries D Alkaline", "PK", {"raw": "12/PK", "inner_count": 12, "inner_size": 1, "inner_uom": "EA"}, 18.00),
        ("ELEC-FLSH-2D", "Flashlight 2D LED", "EA", None, 12.50),
        ("ELEC-FLSH-HD", "Headlamp LED 200 lumen", "EA", None, 18.00),
        ("ELEC-EXT-25", "Extension Cord 25 ft 12/3 SJTW", "EA", None, 32.00),
        ("ELEC-EXT-50", "Extension Cord 50 ft 12/3 SJTW", "EA", None, 48.00),
        ("ELEC-PWR-STRP", "Power Strip 6 outlet surge", "EA", None, 15.00),
        ("STOR-BIN-SM", "Parts Bin Small 4x5x3", "PK", {"raw": "12/PK", "inner_count": 12, "inner_size": 1, "inner_uom": "EA"}, 24.00),
        ("STOR-BIN-MD", "Parts Bin Medium 6x9x5", "PK", {"raw": "6/PK", "inner_count": 6, "inner_size": 1, "inner_uom": "EA"}, 28.00),
        ("STOR-BIN-LG", "Parts Bin Large 8x15x7", "PK", {"raw": "4/PK", "inner_count": 4, "inner_size": 1, "inner_uom": "EA"}, 32.00),
        ("STOR-TOTE-27", "Storage Tote 27 gallon with lid", "EA", None, 14.50),
        ("SIGN-WARN-SLP", "Caution Wet Floor Sign bilingual", "EA", None, 28.00),
        ("SIGN-EXIT", "Exit Sign LED red", "EA", None, 35.00),
        ("SIGN-NO-SMK", "No Smoking Sign 10x14", "EA", None, 8.50),
        ("SIGN-HRD-HAT", "Hard Hat Required Sign 10x14", "EA", None, 8.50),
        ("FAID-KIT-25", "First Aid Kit 25 person", "EA", None, 45.00),
        ("FAID-KIT-50", "First Aid Kit 50 person", "EA", None, 75.00),
        ("FAID-KIT-REF", "First Aid Kit Refill", "EA", None, 28.00),
        ("FIRE-EXT-ABC", "Fire Extinguisher ABC 5 lb", "EA", None, 55.00),
        ("SPILL-KIT-OIL", "Spill Kit Oil-Only 20 gallon", "EA", None, 125.00),
        ("SPILL-PAD-OIL", "Absorbent Pads Oil-Only 15x18", "100/CS", {"raw": "100/CS", "inner_count": 100, "inner_size": 1, "inner_uom": "EA"}, 85.00),
        ("SPILL-SOCK-OIL", "Absorbent Sock Oil-Only 3x48", "12/CS", {"raw": "12/CS", "inner_count": 12, "inner_size": 1, "inner_uom": "EA"}, 65.00),
        ("FLOOR-MAT-ENT", "Entrance Mat 3x5 charcoal", "EA", None, 45.00),
        ("FLOOR-MAT-FAT", "Anti-Fatigue Mat 2x3 black", "EA", None, 38.00),
    ]
    
    for mcode, mdesc, muom, mpack, mprice in misc_items:
        if len(catalog) >= 300:
            break
        sku = mcode
        price = round(mprice * random.uniform(0.95, 1.05), 2)
        catalog.append({
            "sku": sku,
            "description": mdesc,
            "uom": muom,
            "pack": mpack,
            "price": price,
            "erp_product_id": erp_id,
            "category": "MISC"
        })
        erp_id += 1
    
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
    
    return catalog


if __name__ == "__main__":
    catalog = generate_catalog(Path(__file__).parent / "data" / "catalog.json")
    print(f"Generated {len(catalog)} items")
