"""Acceso a las fuentes crudas: por API (corridas reales) o por carpeta (sample/input para pruebas).

Las dos implementaciones exponen la misma interfaz, así el pipeline no sabe de dónde vienen los datos.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx

_MIN_INTERVAL = 60 / 540  # ~9 req/s, por debajo del límite de 600/min


class ApiSource:
    """Cliente del API de fuentes (api/fuentes.openapi.yaml). Respeta el rate limit y reintenta 429/5xx."""

    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.http = httpx.Client(
            headers={"Authorization": f"Bearer {token}"}, timeout=60, follow_redirects=True
        )
        self._lock = threading.Lock()
        self._last = 0.0
        self.requests = 0

    def _throttle(self) -> None:
        with self._lock:
            wait = self._last + _MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def _get(self, path: str) -> httpx.Response:
        r = None
        for attempt in range(6):
            self._throttle()
            self.requests += 1
            try:
                r = self.http.get(f"{self.base}{path}")
            except httpx.TransportError:
                time.sleep(2**attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                retry = r.headers.get("Retry-After")
                time.sleep(float(retry) if retry and retry.isdigit() else 2**attempt)
                continue
            r.raise_for_status()
            return r
        if r is not None:
            r.raise_for_status()
        raise RuntimeError(f"no se pudo descargar {path}")

    def _json(self, path: str):
        return self._get(path).json()

    def record_index(self) -> dict:
        return self._json("/record_index")

    def channels(self) -> list:
        return self._json("/chats/channels")

    def users(self) -> list:
        return self._json("/chats/users")

    def channel_dates(self, canal: str) -> list:
        return self._json(f"/chats/{canal}")

    def messages(self, canal: str, fecha: str) -> list:
        return self._json(f"/chats/{canal}/{fecha}")

    def docs_index(self) -> list:
        return self._json("/docs")

    def doc_bytes(self, doc: dict) -> bytes:
        return self._get(f"/docs/{doc['id']}").content

    def table_bytes(self, nombre: str) -> bytes:
        return self._get(f"/tables/{nombre}").content

    def tables(self) -> list:
        return self._json("/tables")


class DirSource:
    """Mismas fuentes leídas de disco, con la estructura de sample/input:
    chats/channels.json, chats/users.json, chats/<canal>/<fecha>.json, docs/index.json, docs/<archivo>,
    tables/<nombre>, record_index.json.
    """

    def __init__(self, root: str | Path, record_index_path: str | Path | None = None):
        self.root = Path(root)
        self.ri = Path(record_index_path) if record_index_path else self._find("record_index.json")

    def _find(self, name: str) -> Path:
        for p in (self.root / name, self.root.parent / name):
            if p.exists():
                return p
        raise FileNotFoundError(name)

    def _load(self, rel: str):
        return json.loads((self.root / rel).read_text(encoding="utf-8"))

    def record_index(self) -> dict:
        return json.loads(self.ri.read_text(encoding="utf-8"))

    def channels(self) -> list:
        return self._load("chats/channels.json")

    def users(self) -> list:
        return self._load("chats/users.json")

    def channel_dates(self, canal: str) -> list:
        d = self.root / "chats" / canal
        return sorted(p.stem for p in d.glob("*.json")) if d.exists() else []

    def messages(self, canal: str, fecha: str) -> list:
        return self._load(f"chats/{canal}/{fecha}.json")

    def docs_index(self) -> list:
        return self._load("docs/index.json")

    def doc_bytes(self, doc: dict) -> bytes:
        for name in (doc.get("filename"), doc.get("id")):
            if name and (self.root / "docs" / name).exists():
                return (self.root / "docs" / name).read_bytes()
        raise FileNotFoundError(doc)

    def table_bytes(self, nombre: str) -> bytes:
        return (self.root / "tables" / nombre).read_bytes()

    def tables(self) -> list:
        names = sorted(p.name for p in (self.root / "tables").iterdir())
        return [{"name": n} for n in names]
