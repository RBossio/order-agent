"""Transport reali verso l'API esterna di Odoo (JSON-RPC, XML-RPC, JSON-2)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import xmlrpc.client
from typing import Any, NoReturn
from urllib.parse import urljoin, urlparse

from ventureorder.connectors.odoo.client import OdooClient
from ventureorder.connectors.odoo.exceptions import (
    OdooAuthError,
    OdooDataError,
    OdooTransientError,
)

_TRANSIENT_HTTP = {502, 503, 504}
_USER_AGENT = "ventureorder-odoo-connector/0.1"


def _raise_from_odoo_name(name: str | None, message: str) -> NoReturn:
    """Traduce il nome eccezione Odoo nella gerarchia del connettore."""
    lowered = (name or "").lower()
    text = message or "errore Odoo"
    if "accessdenied" in lowered or "accesserror" in lowered or "unauthorized" in lowered:
        raise OdooAuthError(text)
    if "validationerror" in lowered or "usererror" in lowered or "missingerror" in lowered:
        raise OdooDataError(text)
    raise OdooDataError(text)


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    """POST JSON. Restituisce ``(status, body_decodificato)``."""
    body = json.dumps(payload).encode("utf-8")
    req_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": _USER_AGENT,
    }
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
            if not raw:
                return status, None
            return status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        parsed: Any
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            parsed = {"message": raw.decode("utf-8", errors="replace")}
        if exc.code in _TRANSIENT_HTTP:
            raise OdooTransientError(f"HTTP {exc.code} da Odoo: {exc.reason}") from exc
        if exc.code in {401, 403}:
            message = parsed.get("message") if isinstance(parsed, dict) else str(parsed)
            raise OdooAuthError(message or f"HTTP {exc.code}") from exc
        message = ""
        name = None
        if isinstance(parsed, dict):
            message = str(parsed.get("message") or parsed.get("error") or "")
            name = parsed.get("name")
        _raise_from_odoo_name(name, message or f"HTTP {exc.code} da Odoo")
    except TimeoutError as exc:
        raise OdooTransientError(f"Timeout verso Odoo: {url}") from exc
    except urllib.error.URLError as exc:
        raise OdooTransientError(f"Connessione a Odoo rifiutata: {exc.reason}") from exc


class JsonRpcOdooClient(OdooClient):
    """Client JSON-RPC (``POST /jsonrpc``, servizio ``common`` / ``object``)."""

    def __init__(
        self,
        url: str,
        db: str,
        username: str,
        password: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.timeout = timeout
        self._uid: int | None = None
        self._version_info: dict[str, Any] | None = None
        self._rpc_id = 0

    @property
    def major_version(self) -> int:
        info = self.version()
        raw = str(info.get("server_version") or "19.0")
        try:
            return int(raw.split(".", 1)[0])
        except ValueError:
            return 19

    def version(self) -> dict[str, Any]:
        """Chiama ``common.version`` (non richiede autenticazione)."""
        if self._version_info is None:
            result = self._call("common", "version", [])
            self._version_info = result if isinstance(result, dict) else {}
        return self._version_info

    def authenticate(self) -> int:
        """Autentica e memorizza l'uid."""
        uid = self._call("common", "authenticate", [self.db, self.username, self.password, {}])
        if not uid:
            raise OdooAuthError(f"Autenticazione fallita per {self.username}@{self.db}")
        self._uid = int(uid)
        return self._uid

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """``object.execute_kw`` — una chiamata = una transazione Odoo."""
        if self._uid is None:
            self.authenticate()
        rpc_args: list[Any] = [self.db, self._uid, self.password, model, method, args]
        if kwargs:
            rpc_args.append(kwargs)
        return self._call("object", "execute_kw", rpc_args)

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
        kwargs: dict[str, Any] = {}
        if fields is not None:
            kwargs["fields"] = fields
        if offset:
            kwargs["offset"] = offset
        if limit is not None:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        result = self.execute_kw(model, "search_read", [domain], kwargs or None)
        return list(result or [])

    def search_count(self, model: str, domain: list[Any]) -> int:
        return int(self.execute_kw(model, "search_count", [domain]) or 0)

    def create(self, model: str, values: dict[str, Any]) -> int:
        return int(self.execute_kw(model, "create", [values]))

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        kwargs = {"fields": fields} if fields is not None else None
        result = self.execute_kw(model, "read", [ids], kwargs)
        return list(result or [])

    def unlink(self, model: str, ids: list[int]) -> bool:
        return bool(self.execute_kw(model, "unlink", [ids]))

    def _call(self, service: str, method: str, args: list[Any]) -> Any:
        self._rpc_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "id": self._rpc_id,
            "params": {"service": service, "method": method, "args": args},
        }
        status, data = _post_json(
            urljoin(self.url + "/", "jsonrpc"),
            payload,
            timeout=self.timeout,
        )
        if status in _TRANSIENT_HTTP:
            raise OdooTransientError(f"HTTP {status} da Odoo")
        if not isinstance(data, dict):
            raise OdooDataError("Risposta JSON-RPC non valida")
        if data.get("error"):
            error = data["error"]
            info = error.get("data") if isinstance(error, dict) else {}
            name = info.get("name") if isinstance(info, dict) else None
            message = ""
            if isinstance(info, dict):
                message = str(info.get("message") or info.get("debug") or "")
            if not message and isinstance(error, dict):
                message = str(error.get("message") or error)
            _raise_from_odoo_name(name, message or "errore JSON-RPC Odoo")
        return data.get("result")


class _TimeoutTransport(xmlrpc.client.Transport):
    """Transport HTTP XML-RPC con timeout esplicito."""

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self.timeout = timeout

    def make_connection(self, host: Any) -> Any:
        connection = super().make_connection(host)
        connection.timeout = self.timeout
        return connection


class _TimeoutSafeTransport(xmlrpc.client.SafeTransport):
    """Transport HTTPS XML-RPC con timeout esplicito."""

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self.timeout = timeout

    def make_connection(self, host: Any) -> Any:
        connection = super().make_connection(host)
        connection.timeout = self.timeout
        return connection


def _xmlrpc_transport(url: str, timeout: float) -> xmlrpc.client.Transport:
    if urlparse(url).scheme == "https":
        return _TimeoutSafeTransport(timeout)
    return _TimeoutTransport(timeout)


class XmlRpcOdooClient(OdooClient):
    """Client XML-RPC (``/xmlrpc/2/common`` e ``/xmlrpc/2/object``)."""

    def __init__(
        self,
        url: str,
        db: str,
        username: str,
        password: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.timeout = timeout
        self._uid: int | None = None
        self._version_info: dict[str, Any] | None = None
        transport = _xmlrpc_transport(self.url, timeout)
        self.common = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/common",
            allow_none=True,
            transport=transport,
        )
        self.models = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/object",
            allow_none=True,
            transport=_xmlrpc_transport(self.url, timeout),
        )

    @property
    def major_version(self) -> int:
        info = self.version()
        raw = str(info.get("server_version") or "19.0")
        try:
            return int(raw.split(".", 1)[0])
        except ValueError:
            return 19

    def version(self) -> dict[str, Any]:
        if self._version_info is None:
            try:
                version = self.common.version()
                self._version_info = version if isinstance(version, dict) else {}
            except (ConnectionRefusedError, TimeoutError, OSError, xmlrpc.client.ProtocolError) as exc:
                raise OdooTransientError(f"Connessione XML-RPC a Odoo fallita: {exc}") from exc
        return self._version_info

    def authenticate(self) -> int:
        try:
            uid = self.common.authenticate(self.db, self.username, self.password, {})
        except (ConnectionRefusedError, TimeoutError, OSError, xmlrpc.client.ProtocolError) as exc:
            raise OdooTransientError(f"Connessione XML-RPC a Odoo fallita: {exc}") from exc
        if not uid:
            raise OdooAuthError(f"Autenticazione fallita per {self.username}@{self.db}")
        self._uid = int(str(uid))
        return self._uid

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        if self._uid is None:
            self.authenticate()
        try:
            return self.models.execute_kw(
                self.db,
                self._uid,
                self.password,
                model,
                method,
                args,
                kwargs or {},
            )
        except xmlrpc.client.Fault as exc:
            _raise_from_odoo_name(exc.faultCode if isinstance(exc.faultCode, str) else None, exc.faultString)
        except (ConnectionRefusedError, TimeoutError, OSError, xmlrpc.client.ProtocolError) as exc:
            raise OdooTransientError(f"Chiamata XML-RPC a Odoo fallita: {exc}") from exc

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
        kwargs: dict[str, Any] = {}
        if fields is not None:
            kwargs["fields"] = fields
        if offset:
            kwargs["offset"] = offset
        if limit is not None:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order
        return list(self.execute_kw(model, "search_read", [domain], kwargs) or [])

    def search_count(self, model: str, domain: list[Any]) -> int:
        return int(self.execute_kw(model, "search_count", [domain]) or 0)

    def create(self, model: str, values: dict[str, Any]) -> int:
        return int(self.execute_kw(model, "create", [values]))

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        kwargs = {"fields": fields} if fields is not None else None
        return list(self.execute_kw(model, "read", [ids], kwargs) or [])

    def unlink(self, model: str, ids: list[int]) -> bool:
        return bool(self.execute_kw(model, "unlink", [ids]))


class Json2OdooClient(OdooClient):
    """Client API JSON-2 di Odoo 19 (``POST /json/2/<model>/<method>``)."""

    def __init__(
        self,
        url: str,
        db: str,
        api_key: str,
        *,
        timeout: float = 30.0,
        major_version: int = 19,
    ) -> None:
        self.url = url.rstrip("/")
        self.db = db
        self.api_key = api_key
        self.timeout = timeout
        self._major_version = major_version

    @property
    def major_version(self) -> int:
        return self._major_version

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
        body: dict[str, Any] = {"domain": domain}
        if fields is not None:
            body["fields"] = fields
        if offset:
            body["offset"] = offset
        if limit is not None:
            body["limit"] = limit
        if order:
            body["order"] = order
        result = self._call(model, "search_read", body)
        return list(result or [])

    def search_count(self, model: str, domain: list[Any]) -> int:
        return int(self._call(model, "search_count", {"domain": domain}) or 0)

    def create(self, model: str, values: dict[str, Any]) -> int:
        result = self._call(model, "create", {"vals_list": [values]})
        if isinstance(result, list):
            return int(result[0])
        return int(result)

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"ids": ids}
        if fields is not None:
            body["fields"] = fields
        result = self._call(model, "read", body)
        return list(result or [])

    def unlink(self, model: str, ids: list[int]) -> bool:
        return bool(self._call(model, "unlink", {"ids": ids}))

    def _call(self, model: str, method: str, body: dict[str, Any]) -> Any:
        if not self.api_key:
            raise OdooAuthError("ODOO_API_KEY / password mancante per JSON-2")
        endpoint = urljoin(self.url + "/", f"json/2/{model}/{method}")
        headers = {
            "Authorization": f"bearer {self.api_key}",
            "X-Odoo-Database": self.db,
        }
        _status, data = _post_json(endpoint, body, headers=headers, timeout=self.timeout)
        return data


def is_odoo_available(url: str | None = None, timeout: float = 3.0) -> bool:
    """True se l'endpoint JSON-RPC di Odoo risponde a ``common.version``."""
    target = (url or os.environ.get("ODOO_URL") or "http://localhost:8069").rstrip("/")
    try:
        client = JsonRpcOdooClient(target, "probe", "probe", "probe", timeout=timeout)
        client.version()
        return True
    except (OdooTransientError, OdooAuthError, OdooDataError, OSError, ValueError):
        return False
