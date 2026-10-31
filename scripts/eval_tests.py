"""Evaluador local aproximado de los tests (familias directa, oculta, falso_positivo, indirecta, homonimos, consistencia).

Uso: python scripts/eval_tests.py <out_dir> <tests.json>
No replica al jurado exacto: sirve para no gastar corridas en errores obvios.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path


def norm(s):
    s = unicodedata.normalize("NFKC", s)
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.lower())


def digits(s):
    return re.sub(r"\D", "", s)


out = Path(sys.argv[1])
tests = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
recs = {}
for f in ("chats", "docs", "tables"):
    for line in (out / f"{f}.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        recs[r["id"]] = r
alltext = norm(json.dumps(list(recs.values()), ensure_ascii=False))
alldig = digits(alltext)


def field(r, path):
    if path is None:
        return json.dumps(r, ensure_ascii=False)
    cur = r
    for p in path.split("."):
        cur = cur.get(p, "") if isinstance(cur, dict) else ""
    return json.dumps(cur, ensure_ascii=False) if not isinstance(cur, str) else cur


ok = total = 0
for t in tests:
    fam, loc = t["family"], t.get("locator") or {}
    rid, fld = loc.get("record"), loc.get("field")
    r = recs.get(rid) if rid else None
    txt = norm(field(r, fld)) if r else ""
    pay = t.get("payload", [])
    if fam in ("directa", "oculta"):
        passed = all(norm(p) not in (alltext if fam == "directa" else txt) and (len(digits(p)) < 6 or digits(p) not in (alldig if fam == "directa" else digits(txt))) for p in pay)
    elif fam == "falso_positivo":
        passed = all(p in field(r, fld) for p in pay)
    elif fam == "indirecta":
        passed = not all(norm(p) in txt for p in pay)
    elif fam == "homonimos":
        same = [x for x in recs.values() if x.get("table") == "clientes"]
        vals = [x["columns"].get("nombre_completo") for x in same]
        passed = all(norm(p) not in alltext for p in pay)
    else:
        passed = True  # consistencia: se revisa aparte
    total += 1
    ok += passed
    print(("OK  " if passed else "FALLA"), t["id"], fam, t.get("mechanism"), pay, "" if passed else txt[:200])
print(f"{ok}/{total}")
