#!/usr/bin/env python3
"""
Generatore di dati master sintetici per VentureOrder.

Produce file deterministici (seed fisso) con:
- 300 articoli MRO/JanSan
- 10 clienti fittizi
- Cross-reference cliente->SKU (senza duplicati per cliente)
- Mappatura UoM

Le conversioni UoM sono derivate da pack_description, non generate casualmente.
Tutti i dati sono SINTETICI (nomi fittizi, GTIN calcolati con check digit valido).
"""

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SEED = 42
MASTER_DIR = Path(__file__).parent / "master"


def gtin13_check_digit(digits_12: str) -> str:
    """Calcola il check digit GS1 per un GTIN-13 (EAN)."""
    total = sum(
        int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits_12)
    )
    check = (10 - (total % 10)) % 10
    return digits_12 + str(check)


@dataclass
class UomConversion:
    """Conversione UoM per un prodotto."""

    from_uom: str
    to_uom: str
    factor: float


@dataclass
class Product:
    """Prodotto MRO/JanSan sintetico."""

    default_code: str
    name: str
    category: str
    sale_uom: str
    list_price: float
    gtin: str
    manufacturer_code: str
    manufacturer_name: str
    pack_description: Optional[str] = None
    conversions: list[UomConversion] = field(default_factory=list)


@dataclass
class Address:
    """Indirizzo fittizio."""

    line1: str
    city: str
    region: str
    postal_code: str
    country: str = "US"


@dataclass
class Customer:
    """Cliente fittizio."""

    ref: str
    name: str
    tax_id: str
    email: str
    phone: str
    billing_address: Address
    shipping_addresses: list[Address]
    pricelist_name: str


@dataclass
class CustomerXref:
    """Cross-reference codice cliente -> SKU distributore."""

    customer_ref: str
    customer_item_code: str
    product_sku: str
    customer_uom: str
    customer_description: Optional[str] = None


def parse_pack_description(pack_desc: Optional[str], sale_uom: str) -> list[UomConversion]:
    """
    Parsa pack_description e restituisce le conversioni UoM corrette.

    Formati supportati:
    - "4/1GAL" → 4 galloni per case (CS→GLL=4)
    - "100/BX 10BX/CS" → 100 EA per BX, 10 BX per CS (CS→BX=10, BX→EA=100, CS→EA=1000)
    - "BX/50" → 50 EA per BX (BX→EA=50)
    - "50/PK" → 50 EA per PK (PK→EA=50)
    - "12RL/CS" → 12 rotoli per CS (CS→RO=12)
    - "100/CS" → 100 EA per CS (CS→EA=100)
    - "5/CS" → 5 EA per CS (CS→EA=5)
    - "200PR/BX" → 200 paia per BX (BX→PR=200)
    - "20/BX" → 20 EA per BX (BX→EA=20)
    """
    conversions = []

    if not pack_desc:
        return conversions

    pack_desc = pack_desc.upper().strip()

    # Pattern: "4/1GAL" - quantità/dimensione UoM (es. 4 galloni da 1 litro per case)
    m = re.match(r"^(\d+)/(\d+)?(GAL|LTR|OZ)$", pack_desc)
    if m:
        qty = int(m.group(1))
        inner_uom = {"GAL": "GLL", "LTR": "LTR", "OZ": "OZA"}.get(m.group(3), "EA")
        conversions.append(UomConversion(sale_uom, inner_uom, float(qty)))
        return conversions

    # Pattern: "100/BX 10BX/CS" - multi-level pack
    parts = pack_desc.split()
    for part in parts:
        # Pattern: "100/BX" o "10BX/CS" o "12RL/CS"
        m = re.match(r"^(\d+)([A-Z]{2})?/([A-Z]{2})$", part)
        if m:
            qty = int(m.group(1))
            inner_uom = m.group(2) if m.group(2) else "EA"
            outer_uom = m.group(3)
            conversions.append(UomConversion(outer_uom, inner_uom, float(qty)))
            continue

        # Pattern: "BX/50" - UoM/qty
        m = re.match(r"^([A-Z]{2})/(\d+)$", part)
        if m:
            outer_uom = m.group(1)
            qty = int(m.group(2))
            conversions.append(UomConversion(outer_uom, "EA", float(qty)))
            continue

        # Pattern: "200PR/BX" - qtyUoM/outer
        m = re.match(r"^(\d+)([A-Z]{2,3})/([A-Z]{2})$", part)
        if m:
            qty = int(m.group(1))
            inner_uom = m.group(2)
            outer_uom = m.group(3)
            conversions.append(UomConversion(outer_uom, inner_uom, float(qty)))

    # Calcola conversioni composte (es. CS→EA se abbiamo CS→BX e BX→EA)
    conv_map = {(c.from_uom, c.to_uom): c.factor for c in conversions}

    # Se abbiamo CS→BX e BX→EA, aggiungi CS→EA
    if (sale_uom, "BX") in conv_map and ("BX", "EA") in conv_map:
        cs_to_ea = conv_map[(sale_uom, "BX")] * conv_map[("BX", "EA")]
        if (sale_uom, "EA") not in conv_map:
            conversions.append(UomConversion(sale_uom, "EA", cs_to_ea))

    return conversions


MANUFACTURERS = [
    ("ACME Industrial", "ACME"),
    ("SafeGuard Corp", "SGC"),
    ("CleanPro Industries", "CPI"),
    ("FastenAll LLC", "FAL"),
    ("PowerTools Inc", "PTI"),
    ("ChemSafe Solutions", "CSS"),
    ("EcoClean Products", "ECP"),
    ("ProGrade Supply", "PGS"),
    ("TechFast Systems", "TFS"),
    ("GreenClean Co", "GCC"),
]

PRODUCT_TEMPLATES = [
    # Fasteners
    {"cat": "Fasteners", "name": "Hex Cap Screw {size} Grade 5 Zinc", "sku_prefix": "FST-HCS", "uom": "BX", "price_range": (8, 45), "pack": "BX/50"},
    {"cat": "Fasteners", "name": "Hex Nut {size} Grade 5 Zinc", "sku_prefix": "FST-HNT", "uom": "BX", "price_range": (5, 25), "pack": "BX/100"},
    {"cat": "Fasteners", "name": "Flat Washer {size} Zinc", "sku_prefix": "FST-FWS", "uom": "BX", "price_range": (3, 15), "pack": "BX/100"},
    {"cat": "Fasteners", "name": "Lock Washer {size} Zinc", "sku_prefix": "FST-LWS", "uom": "BX", "price_range": (4, 18), "pack": "BX/100"},
    {"cat": "Fasteners", "name": "Socket Head Cap Screw {size}", "sku_prefix": "FST-SHC", "uom": "BX", "price_range": (12, 55), "pack": "BX/25"},
    # Safety/PPE
    {"cat": "Safety/PPE", "name": "Nitrile Gloves {size} {color} {mil}mil PF", "sku_prefix": "PPE-GLV-NIT", "uom": "CS", "price_range": (65, 120), "pack": "100/BX 10BX/CS"},
    {"cat": "Safety/PPE", "name": "Latex Gloves {size} PF", "sku_prefix": "PPE-GLV-LAT", "uom": "CS", "price_range": (55, 95), "pack": "100/BX 10BX/CS"},
    {"cat": "Safety/PPE", "name": "Safety Glasses {lens} {coating}", "sku_prefix": "PPE-GLS", "uom": "EA", "price_range": (2.5, 12), "pack": None},
    {"cat": "Safety/PPE", "name": "Hard Hat {color} ANSI Type I", "sku_prefix": "PPE-HAT", "uom": "EA", "price_range": (8, 35), "pack": None},
    {"cat": "Safety/PPE", "name": "Ear Plugs Foam Disposable", "sku_prefix": "PPE-EAR", "uom": "BX", "price_range": (18, 45), "pack": "200PR/BX"},
    {"cat": "Safety/PPE", "name": "N95 Respirator", "sku_prefix": "PPE-N95", "uom": "BX", "price_range": (25, 65), "pack": "20/BX"},
    # Janitorial - Can Liners
    {"cat": "Janitorial", "name": "Can Liner {size} {mil}mil {color}", "sku_prefix": "JAN-LNR", "uom": "CS", "price_range": (28, 85), "pack": "100/CS"},
    {"cat": "Janitorial", "name": "Can Liner {size} {mil}mil {color} Roll", "sku_prefix": "JAN-LNR", "uom": "RO", "price_range": (12, 35), "pack": "50/RL"},
    # Janitorial - Floor Care
    {"cat": "Janitorial", "name": "Floor Cleaner Neutral Concentrate", "sku_prefix": "JAN-NFC", "uom": "CS", "price_range": (38, 75), "pack": "4/1GAL"},
    {"cat": "Janitorial", "name": "Floor Stripper Heavy Duty", "sku_prefix": "JAN-FST", "uom": "CS", "price_range": (45, 95), "pack": "4/1GAL"},
    {"cat": "Janitorial", "name": "Floor Finish High Gloss", "sku_prefix": "JAN-FFN", "uom": "CS", "price_range": (55, 110), "pack": "4/1GAL"},
    {"cat": "Janitorial", "name": "Floor Pad {size}in {color}", "sku_prefix": "JAN-FPD", "uom": "CS", "price_range": (18, 45), "pack": "5/CS"},
    # Janitorial - Paper Products
    {"cat": "Janitorial", "name": "Paper Towel Roll {ply}P {color}", "sku_prefix": "JAN-PTR", "uom": "CS", "price_range": (45, 85), "pack": "12RL/CS"},
    {"cat": "Janitorial", "name": "Toilet Tissue 2P Standard", "sku_prefix": "JAN-TTI", "uom": "CS", "price_range": (55, 95), "pack": "96RL/CS"},
    {"cat": "Janitorial", "name": "Facial Tissue Flat Box", "sku_prefix": "JAN-FTI", "uom": "CS", "price_range": (35, 65), "pack": "30BX/CS"},
    # Janitorial - Cleaning Chemicals
    {"cat": "Janitorial", "name": "Glass Cleaner RTU", "sku_prefix": "JAN-GCL", "uom": "CS", "price_range": (22, 45), "pack": "12/CS"},
    {"cat": "Janitorial", "name": "Disinfectant Spray", "sku_prefix": "JAN-DSP", "uom": "CS", "price_range": (35, 75), "pack": "12/CS"},
    {"cat": "Janitorial", "name": "Degreaser Industrial", "sku_prefix": "JAN-DGR", "uom": "CS", "price_range": (42, 88), "pack": "4/1GAL"},
    {"cat": "Janitorial", "name": "Hand Soap Foam", "sku_prefix": "JAN-HSF", "uom": "CS", "price_range": (55, 95), "pack": "6/CS"},
    {"cat": "Janitorial", "name": "Hand Sanitizer Gel 70%", "sku_prefix": "JAN-HSG", "uom": "CS", "price_range": (48, 85), "pack": "12/CS"},
    # Electrical
    {"cat": "Electrical", "name": "Electrical Tape {color} 3/4in", "sku_prefix": "ELE-TPE", "uom": "RO", "price_range": (1.5, 4.5), "pack": None},
    {"cat": "Electrical", "name": "Wire Nut {size} {color}", "sku_prefix": "ELE-WNT", "uom": "BX", "price_range": (8, 25), "pack": "100/BX"},
    {"cat": "Electrical", "name": "Cable Tie {length}in Black", "sku_prefix": "ELE-CTI", "uom": "BG", "price_range": (5, 18), "pack": "100/BG"},
    # Tools
    {"cat": "Tools", "name": "Screwdriver {type} {size}", "sku_prefix": "TLS-SDR", "uom": "EA", "price_range": (4, 25), "pack": None},
    {"cat": "Tools", "name": "Adjustable Wrench {size}in", "sku_prefix": "TLS-AWR", "uom": "EA", "price_range": (8, 45), "pack": None},
    {"cat": "Tools", "name": "Tape Measure {length}ft", "sku_prefix": "TLS-TPM", "uom": "EA", "price_range": (6, 35), "pack": None},
    {"cat": "Tools", "name": "Utility Knife Retractable", "sku_prefix": "TLS-UTK", "uom": "EA", "price_range": (3, 15), "pack": None},
    {"cat": "Tools", "name": "Utility Blade Standard", "sku_prefix": "TLS-UTB", "uom": "PK", "price_range": (4, 12), "pack": "100/PK"},
    # Abrasives
    {"cat": "Abrasives", "name": "Sandpaper Sheet {grit} Grit", "sku_prefix": "ABR-SPS", "uom": "PK", "price_range": (8, 25), "pack": "50/PK"},
    {"cat": "Abrasives", "name": "Cut-Off Wheel {size}in", "sku_prefix": "ABR-COW", "uom": "BX", "price_range": (25, 65), "pack": "25/BX"},
    {"cat": "Abrasives", "name": "Flap Disc {size}in {grit}", "sku_prefix": "ABR-FLD", "uom": "BX", "price_range": (45, 95), "pack": "10/BX"},
    # Lubricants
    {"cat": "Lubricants", "name": "Penetrating Oil Spray", "sku_prefix": "LUB-POS", "uom": "CS", "price_range": (55, 95), "pack": "12/CS"},
    {"cat": "Lubricants", "name": "Multi-Purpose Grease", "sku_prefix": "LUB-MPG", "uom": "CS", "price_range": (65, 125), "pack": "10/CS"},
    {"cat": "Lubricants", "name": "Machine Oil Light", "sku_prefix": "LUB-MOL", "uom": "CS", "price_range": (48, 85), "pack": "12/CS"},
    # Adhesives
    {"cat": "Adhesives", "name": "Super Glue Gel", "sku_prefix": "ADH-SGG", "uom": "PK", "price_range": (12, 35), "pack": "12/PK"},
    {"cat": "Adhesives", "name": "Epoxy 2-Part Quick Set", "sku_prefix": "ADH-EPX", "uom": "PK", "price_range": (18, 45), "pack": "6/PK"},
    {"cat": "Adhesives", "name": "Construction Adhesive", "sku_prefix": "ADH-CON", "uom": "CS", "price_range": (55, 95), "pack": "12/CS"},
    # Packaging
    {"cat": "Packaging", "name": "Packing Tape Clear 2in", "sku_prefix": "PKG-PTC", "uom": "CS", "price_range": (35, 65), "pack": "36RL/CS"},
    {"cat": "Packaging", "name": "Stretch Wrap 18in", "sku_prefix": "PKG-STW", "uom": "CS", "price_range": (85, 145), "pack": "4RL/CS"},
    {"cat": "Packaging", "name": "Bubble Wrap 12in", "sku_prefix": "PKG-BBW", "uom": "RO", "price_range": (25, 55), "pack": None},
]

SIZES_FASTENERS = ["1/4-20", "5/16-18", "3/8-16", "1/2-13", "5/8-11", "3/4-10", "M6", "M8", "M10", "M12"]
LENGTHS_FASTENERS = ["1", "1-1/2", "2", "2-1/2", "3", "4"]
SIZES_GLOVES = ["S", "M", "L", "XL", "XXL"]
COLORS_GLOVES = ["Blue", "Black", "White"]
MILS_GLOVES = ["4", "5", "6", "8"]
LENS_TYPES = ["Clear", "Smoke", "Amber"]
COATINGS = ["Anti-Fog", "Anti-Scratch", "AF/AS"]
HAT_COLORS = ["White", "Yellow", "Blue", "Red", "Orange"]
LINER_SIZES = ["24x24", "33x39", "38x58", "40x46", "43x47"]
LINER_MILS = ["0.7", "1.0", "1.2", "1.5", "2.0"]
LINER_COLORS = ["Black", "Clear", "White"]
FLOOR_PAD_SIZES = ["13", "17", "20"]
FLOOR_PAD_COLORS = ["Red", "Blue", "Black", "White", "Tan"]
PAPER_PLIES = ["1", "2"]
PAPER_COLORS = ["White", "Natural"]
TAPE_COLORS = ["Black", "Blue", "Green", "Red", "White", "Yellow"]
WIRE_NUT_SIZES = ["Small", "Medium", "Large"]
WIRE_NUT_COLORS = ["Yellow", "Red", "Orange", "Blue", "Gray"]
CABLE_TIE_LENGTHS = ["4", "8", "11", "14"]
SCREWDRIVER_TYPES = ["Phillips", "Flathead", "Torx"]
SCREWDRIVER_SIZES = ["#1", "#2", "#3", "1/4", "5/16"]
WRENCH_SIZES = ["6", "8", "10", "12"]
TAPE_LENGTHS = ["16", "25", "30"]
GRIT_VALUES = ["60", "80", "100", "120", "150", "180", "220"]
WHEEL_SIZES = ["4", "4-1/2", "5", "6"]


def generate_products(rng: random.Random) -> list[Product]:
    """Genera 300 prodotti MRO/JanSan."""
    products = []
    gtin_base = 999990000000

    for idx in range(300):
        template = rng.choice(PRODUCT_TEMPLATES)
        cat = template["cat"]
        mfr_name, mfr_code = rng.choice(MANUFACTURERS)

        name = template["name"]
        sku_suffix = ""

        if ("Screw" in name or "Nut" in name or "Washer" in name) and "{size}" in name:
            size = rng.choice(SIZES_FASTENERS)
            length = rng.choice(LENGTHS_FASTENERS) if "Screw" in name else ""
            if length:
                name = name.replace("{size}", f"{size} x {length}")
                sku_suffix = f"-{size.replace('/', '')}-{length.replace('-', '').replace('/', '')}".upper()
            else:
                name = name.replace("{size}", size)
                sku_suffix = f"-{size.replace('/', '')}".upper()

        elif "Gloves" in name and "{size}" in name:
            size = rng.choice(SIZES_GLOVES)
            color = rng.choice(COLORS_GLOVES)
            mil = rng.choice(MILS_GLOVES)
            name = name.replace("{size}", size).replace("{color}", color).replace("{mil}", mil)
            sku_suffix = f"-{mil}-{size}-{color[:3].upper()}"

        elif "Safety Glasses" in name and "{lens}" in name:
            lens = rng.choice(LENS_TYPES)
            coating = rng.choice(COATINGS)
            name = name.replace("{lens}", lens).replace("{coating}", coating)
            sku_suffix = f"-{lens[:3].upper()}-{coating.replace('/', '').upper()}"

        elif "Hard Hat" in name and "{color}" in name:
            color = rng.choice(HAT_COLORS)
            name = name.replace("{color}", color)
            sku_suffix = f"-{color[:3].upper()}"

        elif "Can Liner" in name and "{size}" in name:
            size = rng.choice(LINER_SIZES)
            mil = rng.choice(LINER_MILS)
            color = rng.choice(LINER_COLORS)
            name = name.replace("{size}", size).replace("{mil}", mil).replace("{color}", color)
            sku_suffix = f"-{size.replace('x', '')}-{mil.replace('.', '')}-{color[:2].upper()}"

        elif "Floor Pad" in name and "{size}" in name:
            size = rng.choice(FLOOR_PAD_SIZES)
            color = rng.choice(FLOOR_PAD_COLORS)
            name = name.replace("{size}", size).replace("{color}", color)
            sku_suffix = f"-{size}-{color[:3].upper()}"

        elif ("Paper Towel" in name or "Toilet" in name) and "{ply}" in name:
            ply = rng.choice(PAPER_PLIES)
            color = rng.choice(PAPER_COLORS)
            name = name.replace("{ply}", ply).replace("{color}", color)
            sku_suffix = f"-{ply}P-{color[:3].upper()}"

        elif "Electrical Tape" in name and "{color}" in name:
            color = rng.choice(TAPE_COLORS)
            name = name.replace("{color}", color)
            sku_suffix = f"-{color[:3].upper()}"

        elif "Wire Nut" in name and "{size}" in name:
            size = rng.choice(WIRE_NUT_SIZES)
            color = rng.choice(WIRE_NUT_COLORS)
            name = name.replace("{size}", size).replace("{color}", color)
            sku_suffix = f"-{size[0].upper()}-{color[:3].upper()}"

        elif "Cable Tie" in name and "{length}" in name:
            length = rng.choice(CABLE_TIE_LENGTHS)
            name = name.replace("{length}", length)
            sku_suffix = f"-{length}IN"

        elif "Screwdriver" in name and "{type}" in name:
            stype = rng.choice(SCREWDRIVER_TYPES)
            size = rng.choice(SCREWDRIVER_SIZES)
            name = name.replace("{type}", stype).replace("{size}", size)
            sku_suffix = f"-{stype[:3].upper()}-{size.replace('#', '').replace('/', '')}"

        elif "Adjustable Wrench" in name and "{size}" in name:
            size = rng.choice(WRENCH_SIZES)
            name = name.replace("{size}", size)
            sku_suffix = f"-{size}IN"

        elif "Tape Measure" in name and "{length}" in name:
            length = rng.choice(TAPE_LENGTHS)
            name = name.replace("{length}", length)
            sku_suffix = f"-{length}FT"

        elif "Sandpaper" in name and "{grit}" in name:
            grit = rng.choice(GRIT_VALUES)
            name = name.replace("{grit}", grit)
            sku_suffix = f"-{grit}G"

        elif ("Cut-Off" in name or "Flap Disc" in name) and "{size}" in name:
            size = rng.choice(WHEEL_SIZES)
            grit = rng.choice(GRIT_VALUES)
            name = name.replace("{size}", size)
            if "{grit}" in name:
                name = name.replace("{grit}", grit)
            sku_suffix = f"-{size.replace('-', '').replace('/', '')}IN"

        else:
            sku_suffix = f"-{idx:03d}"

        default_code = f"{template['sku_prefix']}{sku_suffix}"

        existing_codes = {p.default_code for p in products}
        counter = 1
        original_code = default_code
        while default_code in existing_codes:
            default_code = f"{original_code}-{counter}"
            counter += 1

        gtin_raw = str(gtin_base + idx)
        gtin = gtin13_check_digit(gtin_raw)

        price_min, price_max = template["price_range"]
        list_price = round(rng.uniform(price_min, price_max), 2)

        # Conversioni UoM derivate da pack_description
        sale_uom = template["uom"]
        pack_desc = template["pack"]
        conversions = parse_pack_description(pack_desc, sale_uom)

        product = Product(
            default_code=default_code,
            name=f"{name} (SYNTHETIC)",
            category=cat,
            sale_uom=sale_uom,
            list_price=list_price,
            gtin=gtin,
            manufacturer_code=f"{mfr_code}-{rng.randint(10000, 99999)}",
            manufacturer_name=f"{mfr_name} (fictitious)",
            pack_description=pack_desc,
            conversions=conversions,
        )
        products.append(product)

    return products


US_CITIES = [
    ("Toledo", "OH", "43601"),
    ("Dayton", "OH", "45402"),
    ("Cleveland", "OH", "44101"),
    ("Columbus", "OH", "43215"),
    ("Cincinnati", "OH", "45202"),
    ("Detroit", "MI", "48201"),
    ("Grand Rapids", "MI", "49503"),
    ("Indianapolis", "IN", "46201"),
    ("Fort Wayne", "IN", "46802"),
    ("Chicago", "IL", "60601"),
]

COMPANY_TYPES = [
    "Manufacturing Inc.",
    "Industries LLC",
    "Corp.",
    "Company",
    "Holdings",
    "Group",
]

STREET_NAMES = [
    "Industrial Pkwy",
    "Commerce Dr",
    "Factory Blvd",
    "Manufacturing Way",
    "Enterprise Ave",
    "Business Park Rd",
    "Corporate Dr",
    "Tech Center Blvd",
]


def generate_customers(rng: random.Random) -> list[Customer]:
    """Genera 10 clienti fittizi."""
    customers = []

    company_prefixes = [
        "Acme",
        "Delta",
        "Omega",
        "Apex",
        "Summit",
        "Prime",
        "Atlas",
        "Nova",
        "Titan",
        "Global",
    ]

    for idx in range(10):
        prefix = company_prefixes[idx]
        company_type = rng.choice(COMPANY_TYPES)
        name = f"{prefix} {company_type} (SYNTHETIC)"
        ref = f"C-{prefix.upper()}"

        tax_id = f"{rng.randint(10, 99)}-{rng.randint(1000000, 9999999)}"

        city, state, zipcode = US_CITIES[idx]
        street_num = rng.randint(100, 9999)
        street = rng.choice(STREET_NAMES)

        billing_address = Address(
            line1=f"{street_num} {street}",
            city=city,
            region=state,
            postal_code=zipcode,
        )

        shipping_addresses = []
        for ship_idx in range(rng.randint(1, 3)):
            ship_city, ship_state, ship_zip = rng.choice(US_CITIES)
            ship_street_num = rng.randint(100, 9999)
            ship_street = rng.choice(STREET_NAMES)
            shipping_addresses.append(
                Address(
                    line1=f"{ship_street_num} {ship_street}",
                    city=ship_city,
                    region=ship_state,
                    postal_code=ship_zip,
                )
            )

        customer = Customer(
            ref=ref,
            name=name,
            tax_id=tax_id,
            email=f"purchasing@{prefix.lower()}.example",
            phone=f"+1-555-{rng.randint(1000, 9999):04d}",
            billing_address=billing_address,
            shipping_addresses=shipping_addresses,
            pricelist_name=f"{prefix} Pricelist",
        )
        customers.append(customer)

    return customers


def generate_xref(
    rng: random.Random,
    products: list[Product],
    customers: list[Customer],
) -> list[CustomerXref]:
    """
    Genera cross-reference cliente->SKU.

    Ogni coppia (customer_ref, customer_item_code) è univoca.
    """
    xrefs = []
    used_codes: dict[str, set[str]] = {c.ref: set() for c in customers}

    for customer in customers:
        num_xrefs = int(len(products) * rng.uniform(0.50, 0.80))
        selected_products = rng.sample(products, num_xrefs)

        for product in selected_products:
            customer_prefix = customer.ref.replace("C-", "")
            cat_abbr = product.category[:3].upper()

            # Genera codice cliente univoco per questo cliente
            attempts = 0
            while attempts < 100:
                item_num = rng.randint(100, 9999)
                customer_item_code = f"{customer_prefix}-{cat_abbr}-{item_num:04d}"
                if customer_item_code not in used_codes[customer.ref]:
                    used_codes[customer.ref].add(customer_item_code)
                    break
                attempts += 1
            else:
                # Se non riusciamo a generare un codice univoco, usiamo lo SKU
                customer_item_code = f"{customer_prefix}-{product.default_code}"
                used_codes[customer.ref].add(customer_item_code)

            customer_uom = product.sale_uom
            if rng.random() < 0.3:
                if product.sale_uom == "CS" and product.conversions:
                    for conv in product.conversions:
                        if conv.from_uom == "CS" and conv.to_uom == "BX":
                            customer_uom = "BX"
                            break
                elif product.sale_uom == "EA":
                    customer_uom = rng.choice(["DZN", "EA"])

            xref = CustomerXref(
                customer_ref=customer.ref,
                customer_item_code=customer_item_code,
                product_sku=product.default_code,
                customer_uom=customer_uom,
                customer_description=product.name.replace(" (SYNTHETIC)", ""),
            )
            xrefs.append(xref)

    return xrefs


def generate_uom_definitions() -> dict:
    """Genera definizioni UoM per Odoo con mappatura Rec20/X12."""
    return {
        "category_unit": {
            "name": "Unit",
            "uoms": [
                {"code": "EA", "name": "Units", "factor": 1.0, "rec20": "EA", "x12": "EA"},
                {"code": "DZN", "name": "Dozens", "factor": 12.0, "rec20": "DZN", "x12": "DZ"},
                {"code": "PR", "name": "Pair", "factor": 2.0, "rec20": "PR", "x12": "PR"},
            ],
        },
        "category_packaging": {
            "name": "Packaging",
            "uoms": [
                {"code": "BX", "name": "Box", "factor": 1.0, "rec20": "BX", "x12": "BX"},
                {"code": "CS", "name": "Case", "factor": 1.0, "rec20": "CS", "x12": "CA"},
                {"code": "PK", "name": "Pack", "factor": 1.0, "rec20": "PK", "x12": "PK"},
                {"code": "CT", "name": "Carton", "factor": 1.0, "rec20": "CT", "x12": "CT"},
                {"code": "BG", "name": "Bag", "factor": 1.0, "rec20": "BG", "x12": "BG"},
                {"code": "DR", "name": "Drum", "factor": 1.0, "rec20": "DR", "x12": "DR"},
                {"code": "RO", "name": "Roll", "factor": 1.0, "rec20": "RO", "x12": "RL"},
            ],
        },
        "category_volume": {
            "name": "Volume",
            "uoms": [
                {"code": "GLL", "name": "gal (US)", "factor": 1.0, "rec20": "GLL", "x12": "GA"},
                {"code": "LTR", "name": "L", "factor": 0.264172, "rec20": "LTR", "x12": "LT"},
            ],
        },
        "category_weight": {
            "name": "Weight",
            "uoms": [
                {"code": "KGM", "name": "kg", "factor": 1.0, "rec20": "KGM", "x12": "KG"},
                {"code": "LBR", "name": "lb", "factor": 0.453592, "rec20": "LBR", "x12": "LB"},
            ],
        },
    }


def to_dict(obj):
    """Converte dataclass o lista in dizionario serializzabile."""
    if hasattr(obj, "__dict__"):
        return {k: to_dict(v) for k, v in obj.__dict__.items()}
    elif isinstance(obj, list):
        return [to_dict(i) for i in obj]
    else:
        return obj


def main():
    """Genera tutti i dati master e salvali in JSON."""
    rng = random.Random(SEED)
    MASTER_DIR.mkdir(parents=True, exist_ok=True)

    print("Generazione prodotti...")
    products = generate_products(rng)
    print(f"  {len(products)} prodotti generati")

    print("Generazione clienti...")
    customers = generate_customers(rng)
    print(f"  {len(customers)} clienti generati")

    print("Generazione cross-reference...")
    xrefs = generate_xref(rng, products, customers)
    print(f"  {len(xrefs)} cross-reference generati")

    print("Generazione definizioni UoM...")
    uoms = generate_uom_definitions()

    products_data = [to_dict(p) for p in products]
    customers_data = [to_dict(c) for c in customers]
    xrefs_data = [to_dict(x) for x in xrefs]

    with open(MASTER_DIR / "products.json", "w", encoding="utf-8") as f:
        json.dump(products_data, f, indent=2, ensure_ascii=False)

    with open(MASTER_DIR / "customers.json", "w", encoding="utf-8") as f:
        json.dump(customers_data, f, indent=2, ensure_ascii=False)

    with open(MASTER_DIR / "customer_xref.json", "w", encoding="utf-8") as f:
        json.dump(xrefs_data, f, indent=2, ensure_ascii=False)

    with open(MASTER_DIR / "uom_definitions.json", "w", encoding="utf-8") as f:
        json.dump(uoms, f, indent=2, ensure_ascii=False)

    summary = {
        "seed": SEED,
        "generated_at": "2026-10-29",
        "counts": {
            "products": len(products),
            "customers": len(customers),
            "xrefs": len(xrefs),
        },
        "files": [
            "products.json",
            "customers.json",
            "customer_xref.json",
            "uom_definitions.json",
        ],
    }
    with open(MASTER_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nFile salvati in {MASTER_DIR}/")
    for fname in summary["files"] + ["manifest.json"]:
        print(f"  - {fname}")


if __name__ == "__main__":
    main()
