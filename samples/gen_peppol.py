"""Riferimento: VOF -> Peppol BIS Order 3 (UBL 2.1 Order). Profilo SELLER. Dati sintetici."""
import json, sys
from lxml import etree
e = json.load(open(sys.argv[1])); h = e["header"]
def gln(base12):  # GLN sintetico con cifra di controllo GS1 valida
    s = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(base12)))
    return base12 + str((10 - s % 10) % 10)
BUY, SEL = gln("999990000042"), gln("999990000001")
NS = {"": "urn:oasis:names:specification:ubl:schema:xsd:Order-2",
      "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
      "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
CAC, CBC = "{%s}" % NS["cac"], "{%s}" % NS["cbc"]
root = etree.Element("{%s}Order" % NS[""], nsmap={None: NS[""], "cac": NS["cac"], "cbc": NS["cbc"]})
def sub(p, tag, text=None, **attr):
    el = etree.SubElement(p, (CBC if tag.startswith("cbc:") else CAC) + tag[4:], **attr)
    if text is not None: el.text = str(text)
    return el
sub(root, "cbc:CustomizationID", "urn:fdc:peppol.eu:poacc:trns:order:3")
sub(root, "cbc:ProfileID", "urn:fdc:peppol.eu:poacc:bis:ordering:3")
sub(root, "cbc:ID", h["po_number"])
sub(root, "cbc:IssueDate", h["po_date"])
if h.get("notes"): sub(root, "cbc:Note", h["notes"])
sub(root, "cbc:DocumentCurrencyCode", h["currency"])
if h.get("buyer_reference"): sub(root, "cbc:CustomerReference", h["buyer_reference"])
def party(tag, p, g, with_addr):
    pp = sub(sub(root, tag), "cac:Party")
    sub(pp, "cbc:EndpointID", g, schemeID="0088")
    sub(sub(pp, "cac:PartyIdentification"), "cbc:ID", g, schemeID="0088")
    sub(sub(pp, "cac:PartyName"), "cbc:Name", p["name"])
    if with_addr:
        a = p["address"]; pa = sub(pp, "cac:PostalAddress")
        sub(pa, "cbc:StreetName", a["line1"]); sub(pa, "cbc:CityName", a["city"])
        sub(pa, "cbc:PostalZone", a["postal_code"]); sub(pa, "cbc:CountrySubentity", a["region"])
        sub(sub(pa, "cac:Country"), "cbc:IdentificationCode", a["country"])
    sub(sub(pp, "cac:PartyLegalEntity"), "cbc:RegistrationName", p["name"])
party("cac:BuyerCustomerParty", e["buyer"], BUY, True)
party("cac:SellerSupplierParty", e["seller"], SEL, True)
d = sub(root, "cac:Delivery"); dl = sub(d, "cac:DeliveryLocation")
sub(dl, "cbc:ID", e["ship_to"]["code_on_document"])
a = e["ship_to"]["address"]; ad = sub(dl, "cac:Address")
sub(ad, "cbc:StreetName", a["line1"]); sub(ad, "cbc:AdditionalStreetName", a["line2"])
sub(ad, "cbc:CityName", a["city"]); sub(ad, "cbc:PostalZone", a["postal_code"]); sub(ad, "cbc:CountrySubentity", a["region"])
sub(sub(ad, "cac:Country"), "cbc:IdentificationCode", a["country"])
sub(sub(d, "cac:RequestedDeliveryPeriod"), "cbc:EndDate", h["requested_delivery_date"])
if h.get("payment_terms_text"): sub(sub(root, "cac:PaymentTerms"), "cbc:Note", h["payment_terms_text"])
REC20 = {"EA": "EA", "BX": "BX", "CS": "CS", "DZN": "DZN", "GLL": "GLL"}
tot = 0.0; lines = []
for l in e["lines"]:
    r = l["resolution"]; f = r["conversion_factor"] or 1
    price = l["unit_price"] if l["price_uom"] == r["erp_uom"] else round(l["unit_price"] / f, 4)
    amt = round(r["erp_quantity"] * price, 2); tot += amt; lines.append((l, r, price, amt))
mt = sub(root, "cac:AnticipatedMonetaryTotal")
sub(mt, "cbc:LineExtensionAmount", "%.2f" % tot, currencyID=h["currency"])
sub(mt, "cbc:PayableAmount", "%.2f" % tot, currencyID=h["currency"])
for l, r, price, amt in lines:
    li = sub(sub(root, "cac:OrderLine"), "cac:LineItem")
    sub(li, "cbc:ID", l["line_no"])
    sub(li, "cbc:Quantity", ("%f" % r["erp_quantity"]).rstrip("0").rstrip("."), unitCode=REC20[r["erp_uom"]])
    sub(li, "cbc:LineExtensionAmount", "%.2f" % amt, currencyID=h["currency"])
    pr = sub(li, "cac:Price"); sub(pr, "cbc:PriceAmount", ("%f" % price).rstrip("0").rstrip("."), currencyID=h["currency"])
    sub(pr, "cbc:BaseQuantity", "1", unitCode=REC20[r["erp_uom"]])
    it = sub(li, "cac:Item"); sub(it, "cbc:Description", l["description"]); sub(it, "cbc:Name", l["description"][:100])
    sub(sub(it, "cac:BuyersItemIdentification"), "cbc:ID", l["buyer_item_code"])
    sub(sub(it, "cac:SellersItemIdentification"), "cbc:ID", r["sku"])
    if l.get("manufacturer_part_number"): sub(sub(it, "cac:ManufacturersItemIdentification"), "cbc:ID", l["manufacturer_part_number"])
    if l.get("gtin"): sub(sub(it, "cac:StandardItemIdentification"), "cbc:ID", l["gtin"], schemeID="0160")
open("sample.peppol-order.xml", "wb").write(etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8"))
print("ok total", round(tot, 2))
