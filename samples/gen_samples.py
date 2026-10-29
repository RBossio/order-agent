"""Riferimento: genera export X12 850 ed EDIFACT ORDERS D96A dal VOF (profilo SELLER).
Solo dati sintetici. Non è codice di produzione."""
import json, sys
e = json.load(open(sys.argv[1]))
h = e["header"]; L = e["lines"]
X12_UOM = {"EA":"EA","BX":"BX","CS":"CA","DZN":"DZ","GLL":"GA","PK":"PK","RO":"RL","PR":"PR","C62":"EA","H87":"EA"}

def seller_line(l):
    r = l["resolution"]; f = r["conversion_factor"] or 1
    qty = r["erp_quantity"]
    # prezzo nell'unità ERP: prezzo PO / fattore se il prezzo era espresso nell'unità del cliente
    price = l["unit_price"] if l.get("price_uom") == r["erp_uom"] else round(l["unit_price"] / f, 4)
    return qty, r["erp_uom"], price, r["sku"]

def num(x):
    return ("%f" % x).rstrip("0").rstrip(".")

# ---------- X12 850 004010 ----------
ctrl = "000000101"
isa = "ISA*00*{:<10}*00*{:<10}*ZZ*{:<15}*ZZ*{:<15}*261103*1422*U*00401*{}*0*T*>".format("", "", "ACMEMFG", "DELTAIND", ctrl)
segs = ["ST*850*0001",
        f"BEG*00*SA*{h['po_number']}**{h['po_date'].replace('-','')}",
        f"CUR*BY*{h['currency']}",
        f"REF*DP*{h['buyer_reference']}",
        f"PER*BD*{e['buyer']['contact']['name']}*EM*{e['buyer']['contact']['email']}",
        f"DTM*002*{h['requested_delivery_date'].replace('-','')}"]
for q, p in (("BT", e["bill_to"]), ("ST", e["ship_to"])):
    a = p["address"]
    n1 = f"N1*{q}*{p['name']}" + (f"*92*{p['code_on_document']}" if p.get("code_on_document") else "")
    segs += [n1, "N3*" + a["line1"] + (("*" + a["line2"]) if a.get("line2") else ""),
             f"N4*{a['city']}*{a['region']}*{a['postal_code']}*{a['country']}"]
for l in L:
    qty, uom, price, sku = seller_line(l)
    po1 = f"PO1*{l['line_no']}*{num(qty)}*{X12_UOM[uom]}*{num(price)}**BP*{l['buyer_item_code']}*VP*{sku}"
    if l.get("gtin"): po1 += f"*UK*{l['gtin']}"
    if l.get("manufacturer_part_number"): po1 += f"*MG*{l['manufacturer_part_number']}"
    segs += [po1, f"PID*F****{l['description']}"]
segs.append(f"CTT*{len(L)}")
segs.append(f"SE*{len(segs)+1}*0001")
x12 = [isa, "GS*PO*ACMEMFG*DELTAIND*20261103*1422*101*X*004010"] + segs + ["GE*1*101", f"IEA*1*{ctrl}"]
open("sample.x12.850.txt", "w").write("~\n".join(x12) + "~\n")

# ---------- EDIFACT ORDERS D96A ----------
def esc(t):
    for c in "?+:'": t = t.replace(c, "?" + c)
    return t
U = {"EA":"EA","BX":"BX","CS":"CS","DZN":"DZN","GLL":"GLL","PK":"PK","RO":"RO","PR":"PR"}
m = [ "UNH+1+ORDERS:D:96A:UN",
      f"BGM+220+{h['po_number']}+9",
      f"DTM+137:{h['po_date'].replace('-','')}:102",
      f"DTM+2:{h['requested_delivery_date'].replace('-','')}:102",
      f"FTX+AAI+++{esc(h['notes'])}",
      f"RFF+CR:{esc(h['buyer_reference'])}"]
def nad(q, p):
    a = p["address"]; code = f"{esc(p['code_on_document'])}::92" if p.get("code_on_document") else ""
    street = esc(a["line1"]) + ((":" + esc(a["line2"])) if a.get("line2") else "")
    return f"NAD+{q}+{code}++{esc(p['name'])}+{street}+{esc(a['city'])}+{a['region']}+{a['postal_code']}+{a['country']}"
m += [nad("BY", e["buyer"]), nad("SU", e["seller"]), nad("DP", e["ship_to"]), nad("IV", e["bill_to"]),
      f"CUX+2:{h['currency']}:9"]
for l in L:
    qty, uom, price, sku = seller_line(l)
    m.append(f"LIN+{l['line_no']}" + (f"++{l['gtin']}:SRV" if l.get("gtin") else ""))
    m.append(f"PIA+5+{esc(sku)}:SA")
    m.append(f"PIA+1+{esc(l['buyer_item_code'])}:IN" + (f"+{esc(l['manufacturer_part_number'])}:MF" if l.get("manufacturer_part_number") else ""))
    m += [f"IMD+F++:::{esc(l['description'][:35])}", f"QTY+21:{num(qty)}:{U[uom]}", f"PRI+AAA:{num(price)}"]
m += ["UNS+S", f"CNT+2:{len(L)}"]
m.append(f"UNT+{len(m)+1}+1")
edi = ["UNA:+.? '", "UNB+UNOC:3+ACMEMFG:ZZZ+DELTAIND:ZZZ+261103:1422+101"] + m + ["UNZ+1+101"]
open("sample.edifact.orders.txt", "w").write(edi[0] + "\n" + "'\n".join(edi[1:]) + "'\n")

# ---------- CSV generic (profilo SELLER) ----------
import csv
with open("sample.generic.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["vo_order_id","po_number","po_revision","po_date","customer_ref","ship_to_code","requested_date","currency",
                "line_no","sku","customer_item_code","description","quantity","uom","unit_price","line_amount","match_method","match_score"])
    for l in L:
        qty, uom, price, sku = seller_line(l)
        w.writerow([e["order_id"], h["po_number"], h["po_revision"], h["po_date"], e["buyer"]["resolved"]["erp_partner_ref"],
                    e["ship_to"].get("code_on_document") or "", h["requested_delivery_date"], h["currency"], l["line_no"], sku,
                    l["buyer_item_code"], l["description"], num(qty), uom, num(price), num(l["line_amount"]),
                    l["resolution"]["method"], l["resolution"]["score"]])
print("ok")
