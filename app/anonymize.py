"""POST /anonymize: anonimiza registros nuevos con el mismo registro de personas de la última corrida.

Seguro anti-corridas: mientras ANONYMIZE_READY != "1", responde 503. Así VALIDAR ENTRYPOINT
falla ANTES de gastar una de las 3 corridas mientras el pipeline no esté listo.
"""
from __future__ import annotations

import os

from fastapi import HTTPException


def anonymize_records(source: str, records: list[dict]) -> dict:
    if os.environ.get("ANONYMIZE_READY") != "1":
        raise HTTPException(503, "pipeline aún no listo (ANONYMIZE_READY != 1)")
    # TODO: detectar + reemplazar usando el registro de personas persistido
    return {"records": records, "entities": []}
