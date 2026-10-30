"""Client Odoo in-memory per i test unitari."""

from __future__ import annotations

from typing import Any

from ventureorder.connectors.odoo.client import OdooClient
from ventureorder.connectors.odoo.exceptions import OdooTransientError


class FakeOdooClient(OdooClient):
    """Finto client che memorizza partner, prodotti e ordini in dizionari.

    Permette di simulare:
    - creazione atomica di ``sale.order`` + righe;
    - fallimento transitorio prima o dopo la ``create`` (crash test);
    - fallimento transitorio della ``search_read`` di riconciliazione;
    - assenza di un server Odoo.
    """

    def __init__(self, *, major_version: int = 19) -> None:
        self._major_version = major_version
        self.records: dict[str, dict[int, dict[str, Any]]] = {
            "res.partner": {},
            "product.product": {},
            "uom.uom": {},
            "sale.order": {},
            "sale.order.line": {},
        }
        self._next_id: dict[str, int] = {model: 1 for model in self.records}
        self.calls: list[tuple[str, str, Any]] = []
        self.transient_failures_before_success = 0
        self.fail_after_create: Exception | None = None
        self.create_error: Exception | None = None
        self.search_read_transient_after_create = 0
        self._create_called = False

    @property
    def major_version(self) -> int:
        return self._major_version

    def seed_partner(
        self,
        *,
        id: int | None = None,
        name: str = "Acme Manufacturing Inc. (SYNTHETIC)",
        ref: str = "C-ACME",
        **extra: Any,
    ) -> int:
        """Inserisce un cliente di test e restituisce l'id."""
        record = {"name": name, "ref": ref, **extra}
        return self._store("res.partner", record, forced_id=id)

    def seed_product(
        self,
        *,
        id: int | None = None,
        name: str = "Prodotto sintetico",
        default_code: str = "SKU-001",
        uom_id: int = 1,
        **extra: Any,
    ) -> int:
        """Inserisce un prodotto di test e restituisce l'id."""
        record = {"name": name, "default_code": default_code, "uom_id": uom_id, **extra}
        return self._store("product.product", record, forced_id=id)

    def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str] | None = None,
        *,
        offset: int = 0,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append((model, "search_read", domain))
        if (
            model == "sale.order"
            and self._create_called
            and self.search_read_transient_after_create > 0
        ):
            self.search_read_transient_after_create -= 1
            raise OdooTransientError("errore transitorio simulato in search_read")
        matched = [dict(rec) for rec in self.records.get(model, {}).values() if self._match(rec, domain)]
        if order:
            field = order.split()[0]
            reverse = order.lower().endswith("desc")
            matched.sort(key=lambda rec: rec.get(field) or 0, reverse=reverse)
        if offset:
            matched = matched[offset:]
        if limit is not None:
            matched = matched[:limit]
        if fields is not None:
            wanted = set(fields) | {"id"}
            matched = [{key: rec.get(key) for key in wanted if key in rec} for rec in matched]
        return matched

    def search_count(self, model: str, domain: list[Any]) -> int:
        self.calls.append((model, "search_count", domain))
        return sum(1 for rec in self.records.get(model, {}).values() if self._match(rec, domain))

    def create(self, model: str, values: dict[str, Any]) -> int:
        self.calls.append((model, "create", values))
        self._create_called = True
        if self.transient_failures_before_success > 0:
            self.transient_failures_before_success -= 1
            raise OdooTransientError("errore transitorio simulato prima della create")
        if self.create_error is not None:
            raise self.create_error
        stored = dict(values)
        line_commands = stored.pop("order_line", None)
        new_id = self._store(model, stored)
        if model == "sale.order":
            order = self.records[model][new_id]
            order.setdefault("state", "draft")
            order.setdefault("name", f"S{new_id:05d}")
            line_ids = self._create_order_lines(new_id, line_commands or [])
            order["order_line"] = line_ids
            order["amount_untaxed"] = self._amount_untaxed(line_ids)
        if self.fail_after_create is not None:
            exc = self.fail_after_create
            self.fail_after_create = None
            raise exc
        return new_id

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append((model, "read", ids))
        rows: list[dict[str, Any]] = []
        for rec_id in ids:
            rec = self.records.get(model, {}).get(rec_id)
            if rec is None:
                continue
            if fields is None:
                rows.append(dict(rec))
            else:
                wanted = set(fields) | {"id"}
                rows.append({key: rec.get(key) for key in wanted if key in rec})
        return rows

    def unlink(self, model: str, ids: list[int]) -> bool:
        self.calls.append((model, "unlink", ids))
        table = self.records.setdefault(model, {})
        for rec_id in ids:
            table.pop(rec_id, None)
        return True

    def created_orders(self) -> list[dict[str, Any]]:
        """Ordini attualmente in memoria (per le asserzioni)."""
        return [dict(rec) for rec in self.records["sale.order"].values()]

    def _store(self, model: str, values: dict[str, Any], forced_id: int | None = None) -> int:
        table = self.records.setdefault(model, {})
        if forced_id is not None:
            rec_id = forced_id
            self._next_id[model] = max(self._next_id.get(model, 1), rec_id + 1)
        else:
            rec_id = self._next_id.setdefault(model, 1)
            self._next_id[model] = rec_id + 1
        record = dict(values)
        record["id"] = rec_id
        table[rec_id] = record
        return rec_id

    def _create_order_lines(self, order_id: int, commands: list[Any]) -> list[int]:
        line_ids: list[int] = []
        for command in commands:
            if not isinstance(command, list | tuple) or len(command) < 3:
                continue
            op, _unused, vals = command[0], command[1], command[2]
            if op != 0 or not isinstance(vals, dict):
                continue
            line = dict(vals)
            line["order_id"] = order_id
            line_ids.append(self._store("sale.order.line", line))
        return line_ids

    def _amount_untaxed(self, line_ids: list[int]) -> float:
        total = 0.0
        for line_id in line_ids:
            line = self.records["sale.order.line"][line_id]
            qty = float(line.get("product_uom_qty") or 0)
            price = float(line.get("price_unit") or 0)
            discount = float(line.get("discount") or 0)
            total += qty * price * (1 - discount / 100.0)
        return round(total, 2)

    def _match(self, record: MappingLike, domain: list[Any]) -> bool:
        if not domain:
            return True
        return all(self._match_term(record, term) for term in domain)

    def _match_term(self, record: MappingLike, term: Any) -> bool:
        if not isinstance(term, list | tuple) or len(term) < 3:
            return True
        field, operator, value = term[0], term[1], term[2]
        current = record.get(field)
        if operator == "=":
            return bool(current == value)
        if operator == "!=":
            return bool(current != value)
        if operator == "in":
            return bool(current in value)
        if operator == "not in":
            return bool(current not in value)
        if operator == "child_of":
            return self._child_of(record, field, value)
        if operator == "ilike":
            return str(value).strip("%").lower() in str(current or "").lower()
        return False

    def _child_of(self, record: MappingLike, field: str, parent_id: Any) -> bool:
        current = record.get(field)
        if current == parent_id or record.get("id") == parent_id:
            return True
        partner_id = current if field == "partner_id" else record.get("id")
        partner = self.records.get("res.partner", {}).get(partner_id) if partner_id else None
        if not partner:
            return False
        return bool(
            partner.get("id") == parent_id
            or partner.get("parent_id") == parent_id
            or partner.get("commercial_partner_id") == parent_id
        )


MappingLike = dict[str, Any]
