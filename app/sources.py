"""Cliente del API de fuentes (api/fuentes.openapi.yaml).

Respeta el límite de 600 req/min y reintenta 429/5xx con espera creciente.
"""
from __future__ import annotations

import threading
import time

import httpx

_MIN_INTERVAL = 60 / 540  # ~9 req/s, por debajo del límite de 600/min


class SourcesClient:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.http = httpx.Client(
            headers={"Authorization": f"Bearer {token}"}, timeout=60, follow_redirects=True
        )
        self._lock = threading.Lock()
        self._last = 0.0

    def _throttle(self) -> None:
        with self._lock:
            wait = self._last + _MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def get(self, path: str) -> httpx.Response:
        for attempt in range(6):
            self._throttle()
            r = self.http.get(f"{self.base}{path}")
            if r.status_code == 429 or r.status_code >= 500:
                retry = r.headers.get("Retry-After")
                time.sleep(float(retry) if retry and retry.isdigit() else 2**attempt)
                continue
            r.raise_for_status()
            return r
        r.raise_for_status()
        return r

    def json(self, path: str):
        return self.get(path).json()

    def bytes(self, path: str) -> bytes:
        return self.get(path).content

    # --- atajos del contrato ---
    def record_index(self) -> dict:
        return self.json("/record_index")

    def channels(self) -> list:
        return self.json("/chats/channels")

    def users(self) -> list:
        return self.json("/chats/users")

    def channel_dates(self, canal: str) -> list:
        return self.json(f"/chats/{canal}")

    def messages(self, canal: str, fecha: str) -> list:
        return self.json(f"/chats/{canal}/{fecha}")

    def docs_index(self) -> list:
        return self.json("/docs")

    def doc(self, doc_id: str) -> bytes:
        return self.bytes(f"/docs/{doc_id}")

    def tables(self) -> list:
        return self.json("/tables")

    def table(self, nombre: str) -> bytes:
        return self.bytes(f"/tables/{nombre}")
