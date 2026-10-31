"""Anonimizador por reglas, guiado por el registro de personas (tablas maestras + users.json).

Flujo:
1. build_people(): personas desde clientes.csv (llave CL-), empleados.xml (KP-) y users.json (uid),
   enlazadas por correo, celular, documento o nombre único. Cada persona trae todas sus formas reales.
2. Por cada campo de texto: spans de identificadores con formato (correo, dictado, celular, cédula...)
   y spans de nombres (variantes completas/parciales, en mayúsculas sin tildes, con _ . -).
   Los nombres sueltos (solo el primer nombre) se reemplazan solo si la persona ya está en el hilo/registro.
3. Reemplazo por spans conservando la forma de la mención (mayúsculas, tildes, separadores).
4. Cuasi-identificadores: ocupación → sector, barrio → ciudad, año de vinculación → "hace unos años".
"""
from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from collections import defaultdict

from app.detectors import find_formatted
from app.entities import EntityStore, apply_spans
from app.pseudonyms import APELLIDOS, NOMBRES_F, NOMBRES_M, SECRET, Registry, guess_gender
from app.textnorm import digits, strip_accents

# ------------------------------------------------------------------ listas

KEEP_TERMS = """Bancolombia Davivienda Nequi Daviplata Superfinanciera PSE Kipi Págalo Pagalo Visa Mastercard Efecty
Baloto Carulla Falabella Rappi DIAN Datacrédito Datacredito TransUnion Movii Bre-B Shakira""".split()
KEEP_PHRASES = ["Kipu Pay", "Superintendencia Financiera", "Plaza Botero", "Banco de Bogotá", "Banco de Occidente",
                "Banco Popular", "Banco Agrario", "Scotiabank Colpatria", "BBVA", "Itaú", "Lulo Bank", "Nu Colombia"]

SECTORES = {
    "comerciante": "trabajador del comercio", "mecanico": "trabajador técnico", "mecánico": "trabajador técnico",
    "contadora": "profesional de finanzas", "contador": "profesional de finanzas", "auxiliar contable": "profesional de finanzas",
    "periodista": "profesional de medios", "community manager": "profesional de medios",
    "abogada": "profesional del derecho", "abogado": "profesional del derecho", "estudiante de derecho": "estudiante",
    "docente": "profesional de la educación", "ingeniera de sistemas": "profesional de tecnología",
    "ingeniero de sistemas": "profesional de tecnología", "conductor de plataforma": "trabajador de transporte",
    "piloto comercial": "trabajador de transporte", "panadero": "trabajador de alimentos", "chef": "trabajador de alimentos",
    "fisioterapeuta": "profesional de la salud", "enfermera": "profesional de la salud", "odontologa": "profesional de la salud",
    "odontóloga": "profesional de la salud", "psicologa": "profesional de la salud", "psicóloga": "profesional de la salud",
    "estudiante de medicina": "estudiante", "veterinaria": "profesional de la salud", "veterinario": "profesional de la salud",
    "administradora": "profesional administrativo", "administrador": "profesional administrativo",
    "electricista": "trabajador técnico", "arquitecto": "profesional de la construcción", "arquitecta": "profesional de la construcción",
    "ingeniero civil": "profesional de la construcción", "diseñador gráfico": "profesional de las industrias creativas",
    "diseñadora gráfica": "profesional de las industrias creativas", "fotógrafa": "profesional de las industrias creativas",
    "fotógrafo": "profesional de las industrias creativas", "estilista": "trabajador de servicios personales",
}
COMMON_WORD_NAMES = {"paz", "luz", "sol", "mar", "flor", "rosa", "angel", "cruz", "leon", "blanca", "dulce", "consuelo",
                     "soledad", "amparo", "socorro", "mercedes", "pilar", "rocio", "esperanza", "gloria", "victoria",
                     "santiago", "trinidad", "milagros", "reyes", "salvador", "lucero", "dolores", "aurora"}


def _h(*parts) -> int:
    return int.from_bytes(hmac.new(SECRET, "\x1f".join(map(str, parts)).encode(), hashlib.sha256).digest()[:8], "big")


def fold(s: str) -> str:
    """Normaliza carácter a carácter (misma longitud): sin tildes, minúsculas."""
    out = []
    for c in s:
        d = unicodedata.normalize("NFD", c)
        base = "".join(x for x in d if unicodedata.category(x) != "Mn") or c
        out.append(base[0].lower() if base else c)
    return "".join(out)


# ------------------------------------------------------------------ personas


class Person:
    def __init__(self, key: str, full_name: str, source: str):
        self.key = key
        self.full = re.sub(r"\s+", " ", full_name.strip())
        self.tokens = self.full.split()
        self.source = source  # cliente | empleado | usuario | tercero
        self.emails: set[str] = set()
        self.phones: set[str] = set()
        self.docs: set[str] = set()
        self.handles: set[str] = set()
        self.births: set[str] = set()
        self.addresses: set[str] = set()
        self.row: dict = {}
        self.uids: set[str] = set()
        self.nick: str = ""

    @property
    def g(self) -> int:  # número de nombres de pila
        n = len(self.tokens)
        if n >= 4:
            return 2
        if n == 3 and fold(self.tokens[1]) in GIVEN_LEX and fold(self.tokens[1]) not in SURNAME_LEX:
            return 2
        return 1

    def variants(self) -> list[str]:
        t = self.tokens
        g = min(self.g, len(t) - 1) if len(t) > 1 else 1
        given, sur = t[:g], t[g:]
        v = {" ".join(t)}
        if sur:
            v.add(" ".join(given + sur[:1]))
            v.add(" ".join(given[:1] + sur[:1]))
            v.add(" ".join(given[:1] + sur))
        if len(given) == 2:
            v.add(" ".join(given))
        return [x for x in v if len(x.split()) >= 2]


EXTRA_GIVEN = '''Wilmer Yesenia Yamid Farid Jhon John Jhonatan Brayan Bryan Kevin Yeison Jeisson Wilson Edwin Edison Fredy Freddy
Jairo Hernando Orlando Alvaro Álvaro Arturo Rubén Hugo Nelson Henry Harold Jader Didier Duván Duvan Robinson Ferney Fabio
Gilberto Humberto Libardo Luis Ignacio Martín Mateo Matías Emilio Esteban Elkin Darío Alexander Alexánder Andrés Felipe
Juan Pedro Pablo Simón Samuel Isaac Alonso Anderson Arley Albeiro Gustavo Reinaldo Oswaldo Octavio Norberto Adrián Ramón
Yuri Yurany Yuliana Leidy Lady Leydi Yenny Jenny Jennifer Johana Yohana Diana Erika Érika Sandra Marisol Maribel Nubia Nohora
Norma Dora Doris Gladys Amparo Alba Elvira Elsa Edith Fanny Graciela Inés Ines Irene Isabel Julia Juana Kelly Karen Karina
Katherine Lorena Luz Lucía Lucia Manuela Marta Martha Miriam Myriam Nancy Natalia Nelly Olga Omaira Piedad Ruth Sara Sonia
Stella Teresa Valentina Vanessa Yolanda Zoraida Alicia Helena Pamela Amalia Kelly Mariana Salomé Antonia Emilia Luciana
Gabriela Isabella Daniela Camila Melissa Melisa Andrea Alejandra Ángela Angela Liliana Paola Viviana Marcela Patricia
Tatiana Juliana Carolina Catalina Fernanda Mónica Monica Claudia Adriana Beatriz Cecilia Clara Rosalba Ximena Jimena
David Daniel Diego Felipe Fernando Ricardo Rodrigo Sergio Mauricio Héctor Hector Javier Jorge Julián Julian Leonardo Manuel
Mario Miguel Nicolás Nicolas Óscar Oscar Rafael Raúl Raul Roberto Santiago Sebastián Sebastian Tomás Tomas Víctor Victor'''.split()
GIVEN_LEX: set[str] = {fold(n) for n in NOMBRES_F + NOMBRES_M + EXTRA_GIVEN}
SURNAME_LEX: set[str] = {fold(a) for a in APELLIDOS}


def build_people(corpus: dict, users: dict) -> tuple[dict[str, Person], dict]:
    people: dict[str, Person] = {}
    idx = {"email": {}, "phone": {}, "doc": {}, "uid": {}, "handle": {}}

    def index(p: Person):
        for e in p.emails:
            idx["email"].setdefault(e.lower(), p.key)
        for ph in p.phones:
            idx["phone"].setdefault(ph, p.key)
        for d in p.docs:
            idx["doc"].setdefault(d, p.key)
        for h in p.handles:
            idx["handle"].setdefault(h.lower(), p.key)

    tables = defaultdict(list)
    for r in corpus["tables"]:
        tables[r["table"]].append(r)

    for r in tables["clientes"]:
        c = r["columns"]
        p = Person(c["cliente_id"], c.get("nombre_completo", ""), "cliente")
        p.row = c
        if c.get("correo"): p.emails.add(c["correo"].strip())
        if c.get("celular"): p.phones.add(digits(c["celular"])[-10:])
        if c.get("num_doc"): p.docs.add(digits(c["num_doc"]))
        if c.get("fecha_nacimiento"): p.births.add(c["fecha_nacimiento"])
        if c.get("direccion"): p.addresses.add(c["direccion"])
        people[p.key] = p
    for r in tables["empleados"]:
        c = r["columns"]
        p = Person(c.get("id") or r["id"].split(":", 1)[1], c.get("nombre", ""), "empleado")
        p.row = c
        if c.get("correo"):
            p.emails.add(c["correo"].strip())
            p.handles.add(c["correo"].split("@")[0])
        if c.get("celular"): p.phones.add(digits(c["celular"])[-10:])
        if c.get("documento"): p.docs.add(digits(c["documento"]))
        if c.get("fecha_nacimiento"): p.births.add(c["fecha_nacimiento"])
        people[p.key] = p
    for p in people.values():
        GIVEN_LEX.add(fold(p.tokens[0])) if p.tokens else None
        for tok in p.tokens[-2:]:
            SURNAME_LEX.add(fold(tok))
        index(p)

    by_name = defaultdict(list)
    for p in people.values():
        by_name[fold(p.full)].append(p.key)

    for uid, u in users.items():
        prof = u.get("profile") or {}
        if u.get("is_bot"):
            continue
        name = prof.get("real_name") or u.get("real_name") or ""
        key = None
        if prof.get("email") and prof["email"].lower() in idx["email"]:
            key = idx["email"][prof["email"].lower()]
        elif prof.get("phone") and digits(prof["phone"])[-10:] in idx["phone"]:
            key = idx["phone"][digits(prof["phone"])[-10:]]
        elif len(by_name.get(fold(name), [])) == 1:
            key = by_name[fold(name)][0]
        if key is None:
            p = Person(f"U:{uid}", name, "usuario")
            people[p.key] = p
            if name and p.tokens:
                GIVEN_LEX.add(fold(p.tokens[0]))
        else:
            p = people[key]
        p.uids.add(uid)
        if prof.get("email"): p.emails.add(prof["email"])
        if prof.get("phone"): p.phones.add(digits(prof["phone"])[-10:])
        if u.get("name"): p.handles.add(u["name"])
        dn = prof.get("display_name") or ""
        if dn and p.tokens and fold(dn) != fold(p.tokens[0]) and " " not in dn.strip():
            p.nick = dn.strip()
        idx["uid"][uid] = p.key
        index(p)
    return people, idx


# ------------------------------------------------------------------ motor


class Anonymizer:
    def __init__(self, corpus: dict, users: dict, registry: Registry):
        self.users = users
        self.people, self.idx = build_people(corpus, users)
        self.registry = registry
        self.store = EntityStore(registry)
        self.written: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
        self.kept_found: dict[str, set] = defaultdict(set)
        self._build_name_index()
        real = set()
        for p in self.people.values():
            real.add(p.full)
            real.update(p.tokens)
        registry.forbid(real)
        from app.textnorm import norm as _n
        for p in self.people.values():
            t = [_n(x) for x in p.tokens]
            for i in range(len(t)):
                for j in range(i + 1, len(t)):
                    registry.forbidden_pairs.add(f"{t[i]} {t[j]}")
            if len(t) >= 3:
                registry.forbidden_pairs.add(" ".join(t[:3]))
                registry.forbidden_pairs.add(" ".join(t[-3:]))
        self.real_values: set[str] = set()
        self.addr_index: dict[str, str] = {}
        self.birth_index: dict[str, str] = {}
        for p in self.people.values():
            self.real_values.update(e.lower() for e in p.emails)
            self.real_values.update(p.phones | p.docs | p.births)
            self.real_values.update(a.lower() for a in p.addresses)
            for a in p.addresses:
                self.addr_index.setdefault(a, p.key)
            for b in p.births:
                self.birth_index.setdefault(b, p.key)
        self.barrios_by_city = defaultdict(set)
        for p in self.people.values():
            if p.source == "cliente" and p.row.get("barrio"):
                self.barrios_by_city[p.row.get("ciudad", "")].add(p.row["barrio"])

    # ---------- índice de nombres

    def _build_name_index(self):
        self.variant_to_keys: dict[str, list[str]] = defaultdict(list)
        for p in sorted(self.people.values(), key=lambda x: x.key):
            for v in p.variants():
                k = fold(v)
                if p.key not in self.variant_to_keys[k]:
                    self.variant_to_keys[k].append(p.key)
        self.name_rx = self._compile(self.variant_to_keys.keys())
        self.given_to_keys: dict[str, list[str]] = defaultdict(list)
        for p in self.people.values():
            if p.tokens:
                self.given_to_keys[fold(p.tokens[0])].append(p.key)
                if p.g == 2:
                    self.given_to_keys[fold(" ".join(p.tokens[:2]))].append(p.key)
            if p.nick:
                self.given_to_keys[fold(p.nick)].append(p.key)
        kept = sorted({fold(x) for x in KEEP_TERMS + KEEP_PHRASES}, key=len, reverse=True)
        self.keep_rx = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(k) for k in kept) + r")(?![a-z0-9])")

    @staticmethod
    def _compile(variants):
        pats = []
        for v in sorted(variants, key=len, reverse=True):
            toks = [re.escape(t) for t in v.split()]
            pats.append(r"[\s_.\-]+".join(toks))
        if not pats:
            return re.compile(r"(?!x)x")
        return re.compile(r"(?<![a-z0-9])(" + "|".join(pats) + r")(?![a-z0-9])")

    # ---------- seudónimos

    def person_entity(self, key: str):
        p = self.people[key]
        e = self.store.get(key, gender=guess_gender(p.tokens[0]) if p.tokens else "x")
        return p, e

    def pseudo_tokens(self, key: str) -> tuple[list[str], list[str]]:
        p, e = self.person_entity(key)
        full = self.registry.pseudonyms_for(key, e.gender, ("name",))["name"].split()
        given, sur = full[:2], full[2:]
        g = p.g if p.tokens else 1
        return given[:g], sur

    def shape_name(self, key: str, original: str) -> str:
        """Seudónimo con la misma forma que la mención (qué tokens, mayúsculas, tildes, separadores)."""
        p = self.people[key]
        given_p, sur_p = self.pseudo_tokens(key)
        parts = re.split(r"([\s_.\-]+)", original)
        toks, seps = parts[0::2], parts[1::2]
        canon = [fold(t) for t in p.tokens]
        g = p.g
        out = []
        used_given = 0
        for tok in toks:
            f = fold(tok)
            role = None
            if f in canon:
                k = canon.index(f)
                role = ("g", k) if k < g else ("s", k - g)
            elif fold(p.nick) == f and p.nick:
                role = ("g", 0)
            if role is None:
                role = ("g", used_given) if not out else ("s", 0)
            kind, i = role
            if kind == "g":
                val = given_p[min(i, len(given_p) - 1)]
                used_given += 1
            else:
                val = sur_p[min(i, len(sur_p) - 1)]
            out.append(self._case_like(tok, val))
        res = toks and out[0] or ""
        for sep, val in zip(seps, out[1:]):
            res += sep + val
        return res

    @staticmethod
    def _case_like(template: str, value: str) -> str:
        letters = [c for c in template if c.isalpha()]
        title = bool(letters) and letters[0].isupper() and not all(c.isupper() for c in letters)
        if template.isascii() and not title:
            value = strip_accents(value)
        if letters and all(c.isupper() for c in letters):
            return value.upper()
        if letters and all(c.islower() for c in letters):
            return value.lower()
        return value

    def pseudo_email(self, key: str, original: str) -> str:
        p, e = self.person_entity(key)
        rec = self.registry.by_key.setdefault(key, {})
        cache = rec.setdefault("emails", {})
        o = original.lower()
        if o in cache:
            return cache[o]
        local, _, domain = o.partition("@")
        gp, sp = self.pseudo_tokens(key)
        gp1 = strip_accents(gp[0]).lower()
        sp1 = strip_accents(sp[0]).lower() if sp else "x"
        gl = strip_accents(p.tokens[0]).lower() if p.tokens else ""
        sl = strip_accents(p.tokens[p.g]).lower() if len(p.tokens) > p.g else ""
        if local in (f"{gl[:1]}{sl}",):
            new_local = f"{gp1[:1]}{sp1}"
        elif "_" in local:
            new_local = f"{gp1}_{sp1}"
        else:
            new_local = f"{gp1}.{sp1}"
        cand, n = f"{new_local}@{domain}", 1
        while cand in self.registry.used or cand == o or cand in self.real_values:
            n += 1
            cand = f"{new_local}{n}@{domain}"
        self.registry.used.add(cand)
        cache[o] = cand
        return cand

    def pseudo_digits(self, key: str, kind: str, original_digits: str) -> str:
        rec = self.registry.by_key.setdefault(key, {})
        cache = rec.setdefault(kind + "s", {})
        if original_digits in cache:
            return cache[original_digits]
        n = len(original_digits)
        for attempt in range(100):
            h = _h(key, kind, original_digits, attempt)
            if kind == "phone":
                val = "3" + original_digits[1:3] + f"{h % 10**7:07d}" if n == 10 else f"{h % 10**n:0{n}d}"
            else:
                first = original_digits[0] if original_digits[0] != "0" else "1"
                val = first + f"{h % 10**(n - 1):0{n - 1}d}"
            if val != original_digits and val not in self.registry.used and val not in self.real_values:
                break
        self.registry.used.add(val)
        cache[original_digits] = val
        return val

    @staticmethod
    def reformat_digits(template: str, new_digits: str) -> str:
        """Mismo formato que el original: 1.107.360.039 → 1.107.252.808, 310 555 1234 → 3xx xxx xxxx."""
        it = iter(new_digits)
        out = []
        for c in template:
            out.append(next(it, "") if c.isdigit() else c)
        rest = "".join(it)
        return "".join(out) + rest

    def pseudo_simple(self, key: str, kind: str, original: str) -> str:
        rec = self.registry.by_key.setdefault(key, {})
        cache = rec.setdefault(kind + "s", {})
        if original in cache:
            return cache[original]
        for attempt in range(50):
            val = self._simple_value(key, kind, original, _h(key, kind, original, attempt))
            if kind == "barrio" or (val.lower() not in self.real_values and val not in self.registry.used):
                break
        self.registry.used.add(val)
        cache[original] = val
        return val

    def _simple_value(self, key: str, kind: str, original: str, h: int) -> str:
        if kind == "birth":
            val = f"{1960 + h % 45}-{(h >> 8) % 12 + 1:02d}-{(h >> 12) % 28 + 1:02d}"
        elif kind == "address":
            tipo = ["Calle", "Carrera", "Transversal", "Diagonal", "Cl", "Cra", "Av"][h % 7]
            val = f"{tipo} {h % 150 + 1} # {(h >> 8) % 99 + 1}-{(h >> 16) % 99 + 1}"
        elif kind == "plate":
            L = "BCDFGHJKLMNPRSTVWXYZ"
            val = "".join(L[(h >> (5 * i)) % 20] for i in range(3)) + f"{(h >> 20) % 1000:03d}"
        elif kind == "passport":
            val = original[:2] + f"{h % 10**(len(original) - 2):0{len(original) - 2}d}" if len(original) > 2 else "AX0000000"
        elif kind == "barrio":
            city = self.people[key].row.get("ciudad", "") if key in self.people else ""
            options = sorted(b for b in self.barrios_by_city.get(city, set()) if b != original) or [original]
            val = options[h % len(options)]
        else:
            val = original
        return val

    # ---------- texto

    def anonymize_text(self, text: str, record_id: str, context: set[str], hints: dict | None = None) -> str:
        """Reemplaza PII en un texto. `context` = llaves de personas activas en el hilo/registro (se amplía)."""
        if not text:
            return text
        spans: list[tuple[int, int, str]] = []
        taken: list[tuple[int, int]] = []

        def free(s, e):
            return all(e <= a or s >= b for a, b in taken)

        def add(s, e, new, key, kind, original):
            if not free(s, e):
                return
            taken.append((s, e))
            spans.append((s, e, new))
            ent = self.store.get(key) if key in self.store.by_key else self.person_entity(key)[1] if key in self.people else self.store.get(key)
            quasi = kind in ("occupation", "barrio_ctx", "year_ctx")
            ent.add("" if quasi else original, record_id, None)
            if not quasi:
                self.written[key][kind].add(new)

        # 1) identificadores con formato
        for s, e, kind, val in find_formatted(text):
            orig = text[s:e]
            if kind in ("email", "email_spoken"):
                key = self.idx["email"].get(val)
                if not key:
                    key = self._third_party("E:" + val, val.split("@")[0].replace(".", " ").replace("_", " ").title())
                new = self.pseudo_email(key, val)
                if kind == "email_spoken":
                    new = new.replace("@", " arroba ").replace(".", " punto ")
                add(s, e, new, key, "email", orig)
                context.add(key)
            elif kind == "phone":
                key = self.idx["phone"].get(val) or self._third_party("PH:" + val, "")
                add(s, e, self.reformat_digits(orig, self.pseudo_digits(key, "phone", val)), key, "phone", orig)
                context.add(key)
            elif kind == "cedula":
                key = self.idx["doc"].get(val)
                if not key:
                    left = fold(text[max(0, s - 30):s])
                    if not re.search(r"(c\.?\s?c\.?|cedula|documento|identificacion|nit)\W*(es|:|no\.?|numero|#)?\W*$", left):
                        continue
                    key = self._third_party("DOC:" + val, "")
                add(s, e, self.reformat_digits(orig, self.pseudo_digits(key, "cedula", val)), key, "cedula", orig)
                context.add(key)
            elif kind == "mention":
                key = self.idx["uid"].get(val)
                if key:
                    context.add(key)
            elif kind in ("plate", "passport"):
                key = self._third_party(kind.upper() + ":" + val, "")
                add(s, e, self.pseudo_simple(key, kind, orig), key, kind, orig)

        # 2) fechas de nacimiento y direcciones conocidas (literales, en todo el corpus)
        for a, key in self.addr_index.items():
            if a in text:
                for m in re.finditer(re.escape(a), text):
                    add(m.start(), m.end(), self.pseudo_simple(key, "address", a), key, "address", a)
        for b, key in self.birth_index.items():
            if b in text:
                for m in re.finditer(r"(?<!\d)" + re.escape(b) + r"(?!\d)", text):
                    add(m.start(), m.end(), self.pseudo_simple(key, "birth", b), key, "birth_iso", b)

        folded = fold(text)
        # 3) organizaciones conservadas (reservan su span para que nadie las toque)
        for m in self.keep_rx.finditer(folded):
            if free(m.start(), m.end()):
                taken.append((m.start(), m.end()))
                self.kept_found[text[m.start():m.end()]].add(record_id)

        # 4) nombres conocidos (variantes de 2+ tokens)
        for m in self.name_rx.finditer(folded):
            s, e = m.span()
            orig = text[s:e]
            norm_v = re.sub(r"[\s_.\-]+", " ", m.group())
            keys = self.variant_to_keys.get(norm_v, [])
            if not keys:
                continue
            key = self._pick(keys, context, hints)
            add(s, e, self.shape_name(key, orig), key, "name", orig)
            context.add(key)

        # 5) terceros: Nombre Apellido con nombre de pila conocido y no registrado
        for m in re.finditer(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñü]+|[A-ZÁÉÍÓÚÑ]{2,})(?:\s+(?:de\s+)?([A-ZÁÉÍÓÚÑ][a-záéíóúñü]+|[A-ZÁÉÍÓÚÑ]{2,})){1,3}\b", text):
            s, e = m.span()
            if not free(s, e):
                continue
            words = m.group().split()
            if fold(words[0]) not in GIVEN_LEX or fold(words[0]) in COMMON_WORD_NAMES:
                continue
            if not any(fold(w) in SURNAME_LEX or fold(w) in GIVEN_LEX for w in words[1:]):
                continue
            key = self._third_party("T:" + fold(m.group()), m.group())
            add(s, e, self.shape_name(key, m.group()), key, "name", m.group())
            context.add(key)

        # 5b) presentaciones explícitas de personas no registradas
        for m in re.finditer(r"(?:\b(?:soy|me llamo|mi nombre es|habla|a nombre de|señora|señor|sra\.?|sr\.?|doña|don)\s+)((?:[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+)(?:\s+(?:de\s+)?[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+){1,3})", text, re.I):
            s, e = m.span(1)
            name = m.group(1)
            if not free(s, e) or not name[:1].isupper() or fold(name.split()[0]) in COMMON_WORD_NAMES:
                continue
            if any(fold(w) in {fold(x) for x in KEEP_TERMS} for w in name.split()):
                continue
            key = self._third_party("T:" + fold(name), name)
            add(s, e, self.shape_name(key, name), key, "name", name)
            context.add(key)

        # 6) nombres sueltos (primer nombre / apodo) de personas activas en el contexto
        if context:
            given_pats = {}
            for key in sorted(context):
                p = self.people.get(key)
                if not p or not p.tokens:
                    continue
                for form in ([" ".join(p.tokens[:2])] if p.g == 2 else []) + [p.tokens[0]] + ([p.nick] if p.nick else []):
                    f = fold(form)
                    if f in COMMON_WORD_NAMES or len(f) < 3:
                        continue
                    given_pats.setdefault(f, key)
            if given_pats:
                rx = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(x) for x in sorted(given_pats, key=len, reverse=True)) + r")(?![a-z0-9])")
                for m in rx.finditer(folded):
                    s, e = m.span()
                    orig = text[s:e]
                    if not orig[:1].isupper() and not ("_" in text[max(0, s - 1):e + 1]):
                        continue
                    key = given_pats[m.group()]
                    add(s, e, self.shape_name(key, orig), key, "name", orig)

        # 7) cuasi-identificadores de clientes activos
        for key in sorted(context):
            p = self.people.get(key)
            if not p or p.source != "cliente":
                continue
            occ = p.row.get("ocupacion", "")
            if occ and fold(occ) in folded:
                i = folded.index(fold(occ))
                if free(i, i + len(occ)):
                    add(i, i + len(occ), SECTORES.get(occ, "trabajador independiente"), key, "occupation", text[i:i + len(occ)])
                    barrio, year = p.row.get("barrio", ""), (p.row.get("fecha_vinculacion") or "")[:4]
                    if barrio and fold(barrio) in folded:
                        j = folded.index(fold(barrio))
                        if free(j, j + len(barrio)):
                            add(j, j + len(barrio), p.row.get("ciudad", "la ciudad"), key, "barrio_ctx", text[j:j + len(barrio)])
                    if year:
                        for mm in re.finditer(rf"(?<!\d){year}(?!\d)", text):
                            if free(*mm.span()):
                                add(mm.start(), mm.end(), "hace unos años", key, "year_ctx", year)

        return apply_spans(text, spans)

    def _pick(self, keys, context, hints):
        for k in keys:
            if k in context:
                return k
        for k in keys:
            if hints and k in hints:
                return k
        return keys[0]

    def _third_party(self, key: str, name: str) -> str:
        if key not in self.people:
            p = Person(key, name or "Persona Desconocida", "tercero")
            self.people[key] = p
        return key

    # ------------------------------------------------------------------ registros

    def chats(self, records: list[dict]) -> list[dict]:
        by_thread = defaultdict(list)
        for r in records:
            by_thread[r["thread_id"]].append(r)
        out = {}
        for tid, msgs in by_thread.items():
            msgs.sort(key=lambda r: float(r["ts"]))
            context: set[str] = set()
            for r in msgs:
                k = self._author_key(r)
                if k:
                    context.add(k)
            # dos pasadas: la primera descubre personas del hilo, la segunda reemplaza con ese contexto
            for r in msgs:
                self._scan_only(r["text"], context)
            for r in msgs:
                new = dict(r)
                k = self._author_key(r)
                if k:
                    new["author"] = self.shape_name(k, r["author"]) if r["author"] else r["author"]
                    self.person_entity(k)[1].add(r["author"], r["id"])
                    self.written[k]["name"].add(new["author"])
                new["text"] = self.anonymize_text(r["text"], r["id"], context)
                new["attachments"] = [{"filename": self.anonymize_text(a.get("filename", ""), r["id"], context)} for a in r["attachments"]]
                out[r["id"]] = new
        return [out[r["id"]] for r in records]

    def _author_key(self, r: dict) -> str | None:
        k = self.idx["uid"].get(r.get("_uid") or "")
        if k or not r.get("author"):
            return k
        keys = self.variant_to_keys.get(fold(r["author"]), [])
        if not keys:
            keys = [p.key for p in self.people.values() if p.tokens and fold(p.full) == fold(r["author"])]
        if keys:
            return keys[0]
        if r.get("_uid") is None and r["author"].strip() and fold(r["author"]) not in {fold(x) for x in KEEP_TERMS}:
            return self._third_party("T:" + fold(r["author"]), r["author"])
        return None

    def touched(self, record_ids: set[str]) -> list[dict]:
        return [e for e in self.entities_json()["entities"] if set(e["records"]) & record_ids]

    def _scan_only(self, text: str, context: set[str]):
        folded = fold(text)
        for m in self.name_rx.finditer(folded):
            keys = self.variant_to_keys.get(re.sub(r"[\s_.\-]+", " ", m.group()), [])
            if len(keys) == 1:
                context.add(keys[0])
        for _, _, kind, val in find_formatted(text):
            k = self.idx["email"].get(val) if kind.startswith("email") else self.idx["phone"].get(val) if kind == "phone" else self.idx["doc"].get(val) if kind == "cedula" else None
            if k:
                context.add(k)

    def docs(self, records: list[dict]) -> list[dict]:
        out = []
        for r in records:
            context: set[str] = set()
            blob = " ".join([r["filename"], r["title"], r["body"]] + list(r["metadata"].values()))
            self._scan_only(blob, context)
            new = dict(r)
            new["filename"] = self.anonymize_text(r["filename"], r["id"], context)
            new["title"] = self.anonymize_text(r["title"], r["id"], context)
            new["body"] = self.anonymize_text(r["body"], r["id"], context)
            new["metadata"] = {k: self.anonymize_text(v, r["id"], context) for k, v in r["metadata"].items()}
            out.append(new)
        return out

    SKIP_COLS = {"cliente_id", "tx_id", "id", "radicado", "monto", "tipo", "estado", "canal", "tipo_doc", "ciudad",
                 "ingreso", "cargo", "fecha_vinculacion"}
    HANDLED_COLS = {"nombre_completo", "nombre", "correo", "celular", "num_doc", "documento", "fecha_nacimiento",
                    "direccion", "ocupacion", "barrio", "cedula", "agente"}

    def tables(self, records: list[dict]) -> list[dict]:
        out = []
        for r in records:
            c = dict(r["columns"])
            rid, t = r["id"], r["table"]
            key = None
            if t == "clientes":
                key = c.get("cliente_id")
            elif t == "empleados":
                key = c.get("id")
            elif c.get("cliente_id") in self.people:
                key = c.get("cliente_id")
            context = {key} if key in self.people else set()
            if t in ("clientes", "empleados") and key in self.people:
                p, e = self.person_entity(key)
                namecol = "nombre_completo" if t == "clientes" else "nombre"
                if c.get(namecol):
                    new = self.shape_name(key, c[namecol]); e.add(c[namecol], rid); self.written[key]["name"].add(new); c[namecol] = new
                ecol = "correo"
                if c.get(ecol):
                    new = self.pseudo_email(key, c[ecol].strip()); e.add(c[ecol], rid); self.written[key]["email"].add(new); c[ecol] = new
                if c.get("celular"):
                    d = digits(c["celular"])[-10:]
                    new = self.reformat_digits(c["celular"], self.pseudo_digits(key, "phone", d)); e.add(c["celular"], rid); self.written[key]["phone"].add(new); c["celular"] = new
                dcol = "num_doc" if t == "clientes" else "documento"
                if c.get(dcol):
                    d = digits(c[dcol])
                    new = self.reformat_digits(c[dcol], self.pseudo_digits(key, "cedula", d)); e.add(c[dcol], rid); self.written[key]["cedula"].add(new); c[dcol] = new
                if c.get("fecha_nacimiento"):
                    new = self.pseudo_simple(key, "birth", c["fecha_nacimiento"]); e.add(c["fecha_nacimiento"], rid); self.written[key]["birth_iso"].add(new); c["fecha_nacimiento"] = new
                if c.get("direccion"):
                    new = self.pseudo_simple(key, "address", c["direccion"]); e.add(c["direccion"], rid); self.written[key]["address"].add(new); c["direccion"] = new
                if t == "clientes":
                    if c.get("ocupacion"):
                        c["ocupacion"] = SECTORES.get(c["ocupacion"], "trabajador independiente")
                    if c.get("barrio"):
                        c["barrio"] = self.pseudo_simple(key, "barrio", c["barrio"])
            if t == "pqrs" and c.get("cedula"):
                d = digits(c["cedula"])
                k2 = self.idx["doc"].get(d) or key or self._third_party("DOC:" + d, "")
                new = self.reformat_digits(c["cedula"], self.pseudo_digits(k2, "cedula", d))
                self.person_entity(k2)[1].add(c["cedula"], rid); self.written[k2]["cedula"].add(new); c["cedula"] = new
            if t == "pqrs" and c.get("agente"):
                k3 = self.idx["handle"].get(c["agente"].lower())
                if k3:
                    gp, sp = self.pseudo_tokens(k3)
                    new = f"{strip_accents(gp[0]).lower()}.{strip_accents(sp[0]).lower()}"
                    self.person_entity(k3)[1].add(c["agente"], rid); self.written[k3]["handle"].add(new); c["agente"] = new
            for col, val in list(c.items()):
                if not val or col in self.SKIP_COLS or col.startswith("fecha") or val == r["columns"].get(col) and col in self.HANDLED_COLS:
                    continue
                if col in self.HANDLED_COLS:
                    continue
                c[col] = self.anonymize_text(val, rid, set(context))
            out.append({**r, "columns": c})
        return out

    # ------------------------------------------------------------------ diccionario

    def entities_json(self) -> dict:
        ents = []
        n = 0
        for key, e in sorted(self.store.by_key.items()):
            if not e.records:
                continue
            n += 1
            w = self.written.get(key, {})
            pseud = {}
            for kind in ("name", "email", "phone", "cedula", "birth_iso", "address", "handle", "plate", "passport"):
                vals = w.get(kind)
                if vals:
                    pseud[kind] = sorted(vals, key=lambda v: (v.isupper() or v.islower(), -len(v), v))[0]
            if "name" not in pseud:
                gp, sp = self.pseudo_tokens(key) if key in self.people else (["Persona"], ["Anónima"])
                pseud["name"] = next(iter(w.get("name", [])), None) or " ".join(gp + sp[:1])
                if not any(pseud["name"] in v for vals in w.values() for v in vals):
                    pseud.pop("name")
                    pseud = pseud or {"name": " ".join(gp + sp[:1])}
            ents.append({"entity_id": f"p_{n:04d}", "type": "person", "originals": sorted(e.originals),
                         "pseudonyms": pseud, "records": sorted(e.records)})
        for i, (term, recs) in enumerate(sorted(self.kept_found.items()), start=1):
            ents.append({"entity_id": f"kept_{i:03d}", "type": "organization_or_place", "originals": [term],
                         "pseudonyms": {}, "kept": True,
                         "reason": "organización, lugar, marca o figura pública; no es persona natural",
                         "records": []})
        return {"entities": ents}
