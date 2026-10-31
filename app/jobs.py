"""Corridas de /run en un hilo en segundo plano. Una sola corrida activa a la vez."""
from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone

from app import storage
from app.pipeline import run_pipeline

_lock = threading.Lock()
_active: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(job_id: str, status: dict) -> None:
    storage.write_json_atomic(storage.run_dir(job_id) / "job.json", status)


def get_status(job_id: str) -> dict | None:
    p = storage.RUNS / job_id / "job.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def start_or_get_active(sources_url: str, token: str) -> str:
    global _active
    with _lock:
        if _active is not None:
            return _active
        job_id = uuid.uuid4().hex[:12]
        _active = job_id
        _save(job_id, {"status": "queued", "started_at": _now()})
    threading.Thread(target=_work, args=(job_id, sources_url, token), daemon=True).start()
    return job_id


def _work(job_id: str, sources_url: str, token: str) -> None:
    global _active
    t0 = time.time()
    status = {"status": "running", "started_at": _now()}
    _save(job_id, status)
    try:
        result = run_pipeline(sources_url.rstrip("/"), token, storage.run_dir(job_id))
        status.update(
            status="done",
            finished_at=_now(),
            records=result.get("records", {}),
            cost={**result.get("cost", {}), "seconds": round(time.time() - t0, 1)},
        )
        _save(job_id, status)
        storage.mark_latest(job_id)  # solo se publica si terminó bien
    except Exception as exc:  # noqa: BLE001 - la corrida debe terminar en failed, nunca colgada
        status.update(status="failed", finished_at=_now(), error=f"{type(exc).__name__}: {exc}")
        _save(job_id, status)
        traceback.print_exc()
    finally:
        with _lock:
            _active = None
