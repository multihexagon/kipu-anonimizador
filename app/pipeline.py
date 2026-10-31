"""Pipeline completo: descarga → normaliza → registro de personas → detecta → reemplaza → valida.

ESQUELETO: por ahora solo baja record_index.json y escribe los 4 archivos vacíos para probar
el flujo de /run → /run/{id} → /output de punta a punta en el despliegue.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.sources import SourcesClient


def run_pipeline(sources_url: str, token: str, out_dir: Path) -> dict:
    client = SourcesClient(sources_url, token)
    index = client.record_index()
    (out_dir / "record_index.json").write_text(json.dumps(index), encoding="utf-8")

    # TODO: ingesta + normalización (chats, docs, tablas)
    # TODO: registro de personas desde clientes.csv, empleados.xml, users.json
    # TODO: detección, resolución, seudónimos deterministas y reemplazo por spans
    for name in ("chats.jsonl", "docs.jsonl", "tables.jsonl"):
        (out_dir / name).write_text("", encoding="utf-8")
    (out_dir / "entities.json").write_text(json.dumps({"entities": []}), encoding="utf-8")

    return {
        "records": {"chats": 0, "docs": 0, "tables": 0},
        "cost": {"tokens_in": 0, "tokens_out": 0},
    }
