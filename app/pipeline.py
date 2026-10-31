"""Pipeline completo: descarga → normaliza → registro de personas → detecta → reemplaza → escribe output/.

Estado actual: descarga y normalización listas. La anonimización (anonymizer.anonymize_corpus)
todavía es un paso identidad: NO usar esta salida para una corrida de evaluación.
"""
from __future__ import annotations

import json
from pathlib import Path

from app import normalize
from app.sources import ApiSource


def run_pipeline(sources_url: str, token: str, out_dir: Path) -> dict:
    return run_from_source(ApiSource(sources_url, token), out_dir)


def run_from_source(src, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    index = src.record_index()
    (out_dir / "record_index.json").write_text(json.dumps(index), encoding="utf-8")

    chats, users = normalize.load_chats(src)
    docs = normalize.load_docs(src)
    tables = normalize.load_tables(src, index)

    corpus = {"chats": chats, "docs": docs, "tables": tables}
    _check_one_to_one(corpus, index)

    # TODO: registro de personas + detección + seudónimos + reemplazo
    entities: list[dict] = []

    for source, recs in corpus.items():
        _write_jsonl(out_dir / f"{source}.jsonl", recs)
    (out_dir / "entities.json").write_text(
        json.dumps({"entities": entities}, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "records": {k: len(v) for k, v in corpus.items()},
        "cost": {"tokens_in": 0, "tokens_out": 0, "requests": getattr(src, "requests", 0)},
    }


def _write_jsonl(path: Path, records: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False) + "\n")
    tmp.replace(path)


def _check_one_to_one(corpus: dict, index: dict) -> None:
    """Falla temprano si la salida no va a ser uno a uno con record_index."""
    problems = []
    for source, recs in corpus.items():
        got = [r["id"] for r in recs]
        want = set(index.get(source, []))
        missing, extra = want - set(got), set(got) - want
        dups = len(got) - len(set(got))
        if missing or extra or dups:
            problems.append(f"{source}: faltan {len(missing)}, sobran {len(extra)}, duplicados {dups}")
    if problems:
        raise RuntimeError("salida no es 1 a 1 con record_index: " + "; ".join(problems))
