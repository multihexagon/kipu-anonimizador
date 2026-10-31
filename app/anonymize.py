"""POST /anonymize: anonimiza registros nuevos con el MISMO registro de personas de la última corrida.

Seguro anti-corridas: mientras no exista app/READY (o ANONYMIZE_READY=1), responde 503, así VALIDAR ENTRYPOINT
falla antes de gastar una corrida si el pipeline no está listo.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from fastapi import HTTPException

from app import storage
from app.anonymizer import Anonymizer
from app.pseudonyms import Registry

_lock = threading.Lock()
_cache: dict = {"stamp": None, "anon": None}


def _anonymizer() -> Anonymizer:
    base = storage.REGISTRY / "base.json"
    reg = storage.REGISTRY / "registry.json"
    if not base.exists():
        if _cache["anon"] is None:
            _cache["anon"] = Anonymizer({"tables": []}, {}, Registry(reg))
        return _cache["anon"]
    stamp = (base.stat().st_mtime, reg.stat().st_mtime if reg.exists() else 0)
    if _cache["stamp"] != stamp:
        data = json.loads(base.read_text(encoding="utf-8"))
        _cache["anon"] = Anonymizer({"tables": data["tables"]}, data["users"], Registry(reg))
        _cache["stamp"] = stamp
    return _cache["anon"]


def anonymize_records(source: str, records: list[dict]) -> dict:
    ready = os.environ.get("ANONYMIZE_READY") == "1" or (Path(__file__).parent / "READY").exists()
    if not ready:
        raise HTTPException(503, "pipeline aún no listo")
    with _lock:
        anon = _anonymizer()
        if source == "chats":
            recs = [{"attachments": [], "thread_id": r.get("id", ""), "ts": "0", **r} for r in records]
            out = anon.chats(recs)
        elif source == "docs":
            recs = [{"filename": "", "title": "", "body": "", "metadata": {}, **r} for r in records]
            out = anon.docs(recs)
        else:
            out = anon.tables([{"columns": {}, "table": (r.get("id", ":").split(":")[0]), **r} for r in records])
        anon.registry.save()  # personas nuevas quedan congeladas para próximas llamadas
        ents = anon.touched({r["id"] for r in records})
    return {"records": out, "entities": ents}
