"""Normalización: de las fuentes crudas al esquema de output/ (ChatRecord, DocRecord, TableRecord).

Esta capa NO anonimiza: produce los registros con los datos reales, uno por id de record_index.
La anonimización trabaja después sobre estos registros.

Puntos a verificar contra sample/expected_output apenas tengamos la muestra (marcados con VERIFICAR).
"""
from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup, Comment
from markdownify import markdownify
from pypdf import PdfReader

# ---------------------------------------------------------------- chats


def load_chats(src) -> tuple[list[dict], dict]:
    """Devuelve (registros de chat, mapa uid -> perfil de usuario)."""
    users = {u["id"]: u for u in src.users()}
    channels = src.channels()

    jobs = [(ch["name"], f) for ch in channels for f in src.channel_dates(ch["name"])]
    with ThreadPoolExecutor(max_workers=6) as pool:
        days = list(pool.map(lambda cf: (cf[0], src.messages(*cf)), jobs))

    records = []
    for canal, msgs in days:
        for m in msgs:
            if not m.get("client_msg_id"):
                continue
            root_ts = m.get("thread_ts") or m["ts"]  # VERIFICAR: hilo = ts del primer mensaje
            records.append(
                {
                    "id": m["client_msg_id"],
                    "thread_id": f"{canal}:{root_ts}",
                    "author": _author_name(m, users),
                    "ts": m["ts"],
                    "text": m.get("text", ""),
                    "attachments": [{"filename": f.get("name") or f.get("title") or ""} for f in m.get("files", [])],
                    "_uid": m.get("user"),  # interno, se quita antes de escribir
                    "_channel": canal,
                }
            )
    return records, users


def _author_name(m: dict, users: dict) -> str:
    u = users.get(m.get("user") or "")
    if u:
        p = u.get("profile") or {}
        return p.get("real_name") or u.get("real_name") or p.get("display_name") or u.get("name") or ""
    return m.get("username") or m.get("bot_profile", {}).get("name") or ""


# ---------------------------------------------------------------- docs


def load_docs(src) -> list[dict]:
    index = src.docs_index()
    with ThreadPoolExecutor(max_workers=6) as pool:
        blobs = list(pool.map(src.doc_bytes, index))
    return [_doc_record(d, b) for d, b in zip(index, blobs)]


def _doc_record(d: dict, raw: bytes) -> dict:
    fmt = d["format"]
    if fmt == "pdf":
        body, title, meta = _pdf(raw)
    elif fmt == "html":
        body, title, meta = _html(raw.decode("utf-8", errors="replace"))
    else:
        body, title, meta = _md(raw.decode("utf-8", errors="replace"))
    return {
        "id": d["id"],
        "format": fmt,
        "filename": d["filename"],
        "title": title or d["filename"],
        "body": body,
        "metadata": {k: ("" if v is None else str(v)) for k, v in meta.items()},
    }


def _pdf(raw: bytes):
    reader = PdfReader(io.BytesIO(raw))
    pages = [(p.extract_text() or "").strip() for p in reader.pages]
    meta = {}
    for k, v in (reader.metadata or {}).items():
        meta[k.lstrip("/").lower()] = v  # VERIFICAR: nombres de claves esperados (author, subject, keywords...)
    title = meta.get("title") or ""
    return "\n\n".join(pages), title, meta


def _html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    meta = {}
    for tag in soup.find_all("meta"):
        key = tag.get("name") or tag.get("property") or tag.get("http-equiv")
        if key and tag.get("content") is not None:
            meta[key] = tag["content"]
    title = soup.title.get_text(strip=True) if soup.title else ""
    comments = [c.strip() for c in soup.find_all(string=lambda s: isinstance(s, Comment))]
    body_el = soup.body or soup
    md = markdownify(str(body_el), heading_style="ATX").strip()
    md = re.sub(r"\n{3,}", "\n\n", md)
    if comments:  # VERIFICAR: posición/forma de los comentarios en la salida ideal
        md += "\n\n" + "\n".join(f"<!-- {c} -->" for c in comments)
    return md, title, meta


_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)


def _md(text: str):
    meta, title = {}, ""
    m = _FM.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")
        title = meta.get("title", "")
    if not title:
        h = re.search(r"^#\s+(.+)$", text, re.M)
        title = h.group(1).strip() if h else ""
    return text, title, meta  # el body conserva el front matter tal cual


# ---------------------------------------------------------------- tables

_TABLE_FILES = {
    "clientes": "clientes.csv",
    "transacciones": "transacciones.csv",
    "pqrs": "pqrs.xml",
    "empleados": "empleados.xml",
}


def load_tables(src, record_index: dict) -> list[dict]:
    wanted: dict[str, set[str]] = {}
    for rid in record_index.get("tables", []):
        t, key = rid.split(":", 1)
        wanted.setdefault(t, set()).add(key)

    out = []
    for table, fname in _TABLE_FILES.items():
        if table not in wanted:
            continue
        raw = src.table_bytes(fname)
        rows = _csv_rows(raw, fname) if fname.endswith(".csv") else _xml_rows(raw)
        key_col = _key_column(rows, wanted.get(table, set()))
        for row in rows:
            out.append({"id": f"{table}:{row[key_col]}", "table": table, "columns": row})
    return out


def _csv_rows(raw: bytes, fname: str) -> list[dict]:
    text = raw.decode("latin-1" if fname == "clientes.csv" else "utf-8-sig")
    sep = ";" if fname == "clientes.csv" else ","
    return [{k: (v or "") for k, v in r.items()} for r in csv.DictReader(io.StringIO(text), delimiter=sep)]


def _xml_rows(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    rows = []
    for el in root:
        row = dict(el.attrib)
        for child in el:
            row[child.tag] = (child.text or "").strip() if len(child) == 0 else ET.tostring(child, encoding="unicode")
        rows.append({k: str(v) for k, v in row.items()})
    return rows


def _key_column(rows: list[dict], keys: set[str]) -> str:
    """La llave es la columna cuyos valores coinciden con los ids de record_index."""
    if not rows:
        return ""
    best, score = next(iter(rows[0])), -1
    for col in rows[0]:
        hits = sum(1 for r in rows if r.get(col) in keys)
        if hits > score:
            best, score = col, hits
    return best
