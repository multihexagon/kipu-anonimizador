"""Entidades (personas y conservados) y reemplazo por spans.

Una Entity acumula todas las formas REALES encontradas y los registros donde aparece; eso alimenta
entities.json (honestidad del diccionario). El reemplazo opera por spans sobre el texto original:
el texto no personal queda byte a byte igual.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.pseudonyms import Registry


@dataclass
class Entity:
    key: str  # llave estable: CL-xxxx, KP-xxx, uid, o sintética para quien solo aparece en texto
    type: str = "person"  # person | organization_or_place
    gender: str = "x"
    originals: set[str] = field(default_factory=set)
    records: set[str] = field(default_factory=set)
    used_kinds: set[str] = field(default_factory=set)  # categorías de seudónimo que se usaron
    kept: bool = False
    reason: str = ""

    def add(self, form: str, record_id: str | None, kind: str | None = None) -> None:
        if form:
            self.originals.add(form)
        if record_id:
            self.records.add(record_id)
        if kind:
            self.used_kinds.add(kind)


class EntityStore:
    def __init__(self, registry: Registry):
        self.registry = registry
        self.by_key: dict[str, Entity] = {}

    def get(self, key: str, **kw) -> Entity:
        e = self.by_key.get(key)
        if e is None:
            e = self.by_key[key] = Entity(key=key, **kw)
        return e

    def pseudo(self, e: Entity, kind: str) -> str:
        """Seudónimo de categoría `kind` para la entidad (congelado en el registro)."""
        e.used_kinds.add(kind)
        return self.registry.pseudonyms_for(e.key, e.gender, ("name", kind) if kind != "name" else ("name",))[kind]

    def to_json(self) -> dict:
        out = []
        for i, e in enumerate(sorted(self.by_key.values(), key=lambda x: x.key), start=1):
            item = {
                "entity_id": f"p_{i:04d}" if e.type == "person" else f"o_{i:04d}",
                "type": e.type,
                "originals": sorted(e.originals),
                "records": sorted(e.records),
            }
            if e.kept:
                item.update(kept=True, reason=e.reason)
            else:
                known = self.registry.by_key.get(e.key, {})
                item["pseudonyms"] = {k: known[k] for k in sorted(e.used_kinds | {"name"}) if k in known}
            out.append(item)
        return {"entities": out}


def apply_spans(text: str, spans: list[tuple[int, int, str]]) -> str:
    """Aplica reemplazos (start, end, nuevo) sin solaparse; gana el span que empieza antes y es más largo."""
    if not spans:
        return text
    spans = sorted(spans, key=lambda s: (s[0], -(s[1] - s[0])))
    out, pos = [], 0
    for start, end, new in spans:
        if start < pos:
            continue
        out.append(text[pos:start])
        out.append(new)
        pos = end
    out.append(text[pos:])
    return "".join(out)


def match_case(template: str, value: str) -> str:
    """Copia la forma de la mención: MAYÚSCULAS sin tildes, minúsculas o tal cual."""
    from app.textnorm import strip_accents

    letters = [c for c in template if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        no_accents = strip_accents(template) == template
        v = strip_accents(value) if no_accents else value
        return v.upper()
    if letters and all(c.islower() for c in letters):
        return value.lower()
    return value
