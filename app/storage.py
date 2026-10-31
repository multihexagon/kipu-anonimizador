"""Disco persistente (volumen de Railway montado en DATA_DIR).

Estructura:
  DATA_DIR/runs/<job_id>/        salida de cada corrida (se escribe aquí primero)
  DATA_DIR/runs/<job_id>/job.json estado de la corrida
  DATA_DIR/LATEST                 id de la última corrida TERMINADA (se cambia de forma atómica)
  DATA_DIR/registry/              registro de personas (seudónimos congelados entre corridas)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
RUNS = DATA_DIR / "runs"
REGISTRY = DATA_DIR / "registry"
LATEST = DATA_DIR / "LATEST"

for d in (RUNS, REGISTRY):
    d.mkdir(parents=True, exist_ok=True)


def run_dir(job_id: str) -> Path:
    d = RUNS / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json_atomic(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def mark_latest(job_id: str) -> None:
    """Publica una corrida terminada. /output nunca ve una corrida a medias."""
    tmp = LATEST.with_suffix(".tmp")
    tmp.write_text(job_id, encoding="utf-8")
    os.replace(tmp, LATEST)


def latest_job_id() -> str | None:
    return LATEST.read_text(encoding="utf-8").strip() if LATEST.exists() else None


def latest_output_path(filename: str) -> Path | None:
    job_id = latest_job_id()
    if not job_id:
        return None
    p = RUNS / job_id / filename
    return p if p.exists() else None
