"""Servicio HTTP del reto "Vende los datos sin vender a la gente".

Contrato: api/participante.openapi.yaml. Raíz /v1, sin autenticación obligatoria
(si llega un header Authorization se acepta y se ignora).
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app import jobs, storage
from app.anonymize import anonymize_records

TEAM = os.environ.get("TEAM_NAME", "kipu-anonimizador")
VERSION = os.environ.get("APP_VERSION", "0.1.0")
MODELS = [m for m in os.environ.get("LLM_MODELS", "").split(",") if m]

app = FastAPI(title="Kipu anonimizador", version=VERSION)

OUTPUT_FILES = {"chats.jsonl", "docs.jsonl", "tables.jsonl", "entities.json"}


class RunRequest(BaseModel):
    sources_url: str
    token: str


class AnonymizeRequest(BaseModel):
    source: str
    records: list[dict]


@app.get("/")
def root():
    return {"status": "ok", "see": "/v1/health"}


@app.get("/v1/health")
def health():
    return {"status": "ok", "team": TEAM, "version": VERSION, "models": MODELS, "busy": jobs.is_busy()}


@app.post("/v1/run", status_code=202)
def run(req: RunRequest):
    # Idempotente: si ya hay una corrida activa, devuelve ese mismo job.
    job_id = jobs.start_or_get_active(req.sources_url, req.token)
    return {"job_id": job_id}


@app.get("/v1/run/{job_id}")
def run_status(job_id: str):
    status = jobs.get_status(job_id)
    if status is None:
        raise HTTPException(404, "job no encontrado")
    return status


@app.get("/v1/output/{archivo}")
def output(archivo: str):
    if archivo not in OUTPUT_FILES:
        raise HTTPException(404, "archivo no válido")
    path = storage.latest_output_path(archivo)
    if path is None:
        raise HTTPException(404, "no hay corrida terminada")
    media = "application/json" if archivo.endswith(".json") else "application/x-ndjson"
    return FileResponse(path, media_type=media)


@app.post("/v1/anonymize")
def anonymize(req: AnonymizeRequest):
    if req.source not in {"chats", "docs", "tables"}:
        raise HTTPException(422, "source debe ser chats, docs o tables")
    if len(req.records) > 50:
        raise HTTPException(422, "máximo 50 registros por lote")
    return anonymize_records(req.source, req.records)


@app.get("/v1/entities")
def entities():
    path = storage.latest_output_path("entities.json")
    if path is None:
        return JSONResponse({"entities": []})
    return FileResponse(path, media_type="application/json")
