"""Detectores por regex de identificadores con formato (no nombres).

Cada detector devuelve spans (start, end, kind, valor_canónico). El valor canónico permite enlazar
la mención con la entidad del registro (p. ej. el correo dictado "juan arroba gmail punto com"
se canoniza a "juan@gmail.com").
"""
from __future__ import annotations

import re

from app.textnorm import digits

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# correo dictado: "lucia ferrer arroba gmail punto com", "lucia.ferrer (arroba) gmail (punto) com"
PHONE = re.compile(r"(?<!\d)(?:\+?57[\s.-]?)?3\d{2}[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
CEDULA = re.compile(r"(?<![\d-])(?:\d{1,3}(?:[.\s]\d{3}){2,3}|\d{6,10})(?![\d-])")
PLATE = re.compile(r"\b[A-Z]{3}[\s-]?\d{3}\b|\b[A-Z]{3}[\s-]?\d{2}[A-Z]\b")
PASSPORT = re.compile(r"\b(?:[A-Z]{2}\d{6,7}|[A-Z]\d{7,8})\b")
SLACK_MENTION = re.compile(r"<@([A-Z0-9]+)(?:\|([^>]+))?>")


_AT = re.compile(r"[\(\[]?\s*\barroba\b\s*[\)\]]?", re.I)
_DOM = re.compile(r"\s*([A-Za-z0-9-]+)((?:\s*[\(\[]?\s*\bpunto\b\s*[\)\]]?\s*[A-Za-z]{2,6}){1,2})", re.I)
_STOP = {"a", "al", "es", "mi", "su", "correo", "email", "mail", "el", "la", "de", "del", "y", "o", "en",
         "con", "por", "para", "que", "como", "tu", "escribe", "escribeme", "escríbeme", "es:", "sería"}
_TOKEN = re.compile(r"[A-Za-z0-9._-]+")


def _spoken_emails(text: str):
    """'lucia ferrer arroba gmail punto com' → (start, end, 'lucia.ferrer@gmail.com').

    El usuario se arma hacia atrás desde 'arroba': máximo 3 tokens, cortando en palabras vacías.
    """
    for at in _AT.finditer(text):
        dm = _DOM.match(text, at.end())
        if not dm:
            continue
        toks = list(_TOKEN.finditer(text[: at.start()]))
        user_toks = []
        for t in reversed(toks):
            w = t.group()
            gap = text[t.end(): (user_toks[0].start() if user_toks else at.start())]
            if w.lower() in _STOP or len(user_toks) >= 3 or gap.strip(" ") != "":
                break
            if w.lower() in {"punto", "guion", "guión"} and not user_toks:
                break
            user_toks.insert(0, t)
        if not user_toks:
            continue
        raw_user = text[user_toks[0].start(): at.start()]
        user = re.sub(r"\s*\bpunto\b\s*", ".", raw_user, flags=re.I)
        user = re.sub(r"\s*\bgui[oó]n\b\s*", "-", user, flags=re.I)
        user = re.sub(r"\s+", ".", user.strip())
        tld = re.sub(r"[\s\(\)\[\]]*\bpunto\b[\s\(\)\[\]]*", ".", dm.group(2), flags=re.I)
        yield user_toks[0].start(), dm.end(), f"{user}@{dm.group(1)}{tld}".lower()


def find_formatted(text: str) -> list[tuple[int, int, str, str]]:
    spans: list[tuple[int, int, str, str]] = []
    for s, e, v in _spoken_emails(text):
        spans.append((s, e, "email_spoken", v))
    for m in EMAIL.finditer(text):
        spans.append((m.start(), m.end(), "email", m.group().lower()))
    for m in PHONE.finditer(text):
        spans.append((m.start(), m.end(), "phone", digits(m.group())[-10:]))
    for m in PLATE.finditer(text):
        spans.append((m.start(), m.end(), "plate", re.sub(r"[\s-]", "", m.group())))
    for m in PASSPORT.finditer(text):
        spans.append((m.start(), m.end(), "passport", m.group()))
    for m in CEDULA.finditer(text):
        spans.append((m.start(), m.end(), "cedula", digits(m.group())))
    for m in SLACK_MENTION.finditer(text):
        spans.append((m.start(), m.end(), "mention", m.group(1)))
    return _drop_overlaps(spans)


def _drop_overlaps(spans):
    """Gana el span más largo; a igual largo, el primero detectado (orden de prioridad de arriba)."""
    spans = sorted(enumerate(spans), key=lambda x: (x[1][0], -(x[1][1] - x[1][0]), x[0]))
    out, end = [], -1
    for _, s in spans:
        if s[0] >= end:
            out.append(s)
            end = s[1]
    return out
