"""Generador de seudónimos deterministas y registro congelado.

Reglas (doc de diseño):
- El seudónimo se CALCULA con HMAC(PSEUDO_SECRET, llave de entidad) → reproducible aunque se pierda el disco.
- Nombre = nombre + segundo nombre + apellido + apellido, del mismo género, colombiano.
- Un seudónimo ya asignado NUNCA se reasigna (registro persistido). Los choques solo los resuelven
  las personas NUEVAS, avanzando un contador dentro de su propio HMAC.
- Nunca se entrega un seudónimo que coincida con una forma real del corpus.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from pathlib import Path

from app.textnorm import norm, strip_accents

SECRET = os.environ.get("PSEUDO_SECRET", "dev-secret-cambiar").encode()

NOMBRES_F = """Adriana Alejandra Ana Andrea Ángela Beatriz Carolina Catalina Claudia Daniela Diana Elena
Esperanza Estefanía Gabriela Gloria Isabel Jimena Juliana Laura Liliana Lorena Luisa Marcela Margarita María
Mariana Mónica Natalia Nathalia Olga Paola Patricia Paula Pilar Rocío Rosa Sandra Silvia Sofía Susana Tatiana
Valeria Verónica Viviana Yolanda Ximena Yuliana Zulma Camila Lina""".split()
NOMBRES_M = """Alberto Alejandro Andrés Antonio Camilo Carlos César Cristian Daniel David Diego Eduardo Esteban
Fabián Felipe Fernando Francisco Gabriel Germán Gonzalo Gustavo Hernán Iván Jaime Javier Jorge José Julián
Leonardo Luis Manuel Mario Mauricio Miguel Nicolás Óscar Pablo Rafael Ramiro Ricardo Roberto Rodrigo Santiago
Sebastián Sergio Tomás Víctor Wilson""".split()
APELLIDOS = """Acosta Aguilar Álvarez Arango Arias Ávila Barrera Benítez Bermúdez Bustos Cabrera Calderón Camacho
Cárdenas Carvajal Castillo Castro Cifuentes Contreras Correa Cortés Cruz Delgado Díaz Duque Escobar Espinosa
Estrada Fajardo Fonseca Franco Fuentes Gallego Garzón Gil Giraldo Guerrero Gutiérrez Henao Herrera Hoyos
Jaramillo Lozano Marín Medina Mejía Mendoza Molina Montoya Mora Moreno Muñoz Navarro Nieto Ochoa Orozco Ortiz
Osorio Ospina Pardo Parra Peña Pineda Pulido Quintero Ramírez Restrepo Reyes Rincón Ríos Rivera Rojas Romero
Salazar Sánchez Sandoval Serna Silva Suárez Tobón Torres Trujillo Uribe Valencia Vargas Vásquez Vega Velásquez
Villegas Zapata Zuluaga""".split()


def _h(*parts: str) -> int:
    msg = "\x1f".join(parts).encode()
    return int.from_bytes(hmac.new(SECRET, msg, hashlib.sha256).digest()[:8], "big")


def _pick(seq, key, salt):
    return seq[_h(key, salt) % len(seq)]


class Registry:
    """Seudónimos asignados, persistidos en disco. Thread-safe para /run y /anonymize."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self.lock = threading.Lock()
        self.by_key: dict[str, dict] = {}  # entity_key -> {name, email, phone, ...}
        self.used: set[str] = set()  # valores ya entregados (normalizados), para unicidad
        self.forbidden: set[str] = set()  # formas reales del corpus (normalizadas)
        self.forbidden_pairs: set[str] = set()  # "nombre apellido" reales, para que un seudónimo parcial no choque
        if path and path.exists():
            self.by_key = json.loads(path.read_text(encoding="utf-8"))
            for p in self.by_key.values():
                for v in p.values():
                    if isinstance(v, str):
                        self.used.add(norm(v))
                    elif isinstance(v, dict):
                        self.used.update(v.values())

    def save(self) -> None:
        if not self.path:
            return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.by_key, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def forbid(self, real_forms) -> None:
        self.forbidden.update(norm(f) for f in real_forms if f)

    # --------------------------------------------------------- asignación

    def pseudonyms_for(self, key: str, gender: str = "x", want: tuple[str, ...] = ("name",)) -> dict:
        """Devuelve (y congela) los seudónimos de una entidad. Lo ya asignado no cambia nunca."""
        with self.lock:
            rec = self.by_key.setdefault(key, {})
            for kind in want:
                if kind not in rec:
                    rec[kind] = self._fresh(kind, key, gender, rec)
            return dict(rec)

    def _fresh(self, kind: str, key: str, gender: str, rec: dict) -> str:
        gen = _GENERATORS[kind]
        for attempt in range(1000):
            val = gen(key, gender, rec, str(attempt))
            n = norm(val)
            if kind == "name":
                t = n.split()
                pairs = {f"{t[0]} {t[2]}", f"{t[1]} {t[2]}", f"{t[0]} {t[1]} {t[2]}", f"{t[0]} {t[2]} {t[3]}"} if len(t) >= 4 else set()
                if pairs & self.forbidden_pairs:
                    continue
            if n not in self.used and n not in self.forbidden:
                self.used.add(n)
                return val
        raise RuntimeError(f"no hay seudónimo libre para {kind}")


# --------------------------------------------------------- generadores por categoría


def _name(key, gender, rec, salt):
    g = gender if gender in ("f", "m") else ("f" if _h(key, "g") % 2 else "m")
    pool = NOMBRES_F if g == "f" else NOMBRES_M
    n1 = _pick(pool, key, "n1" + salt)
    n2 = _pick([n for n in pool if n != n1], key, "n2" + salt)
    a1 = _pick(APELLIDOS, key, "a1" + salt)
    a2 = _pick([a for a in APELLIDOS if a != a1], key, "a2" + salt)
    return f"{n1} {n2} {a1} {a2}"


def _email(key, gender, rec, salt, domain=None):
    parts = strip_accents(rec.get("name") or _name(key, gender, rec, salt)).lower().split()
    first, last = parts[0], parts[2] if len(parts) > 2 else parts[-1]
    dom = domain or _pick(["gmail.com", "hotmail.com", "outlook.com", "yahoo.com"], key, "dom")
    suffix = "" if salt == "0" else str(_h(key, "em" + salt) % 100)
    return f"{first}.{last}{suffix}@{dom}"


def _phone(key, gender, rec, salt):
    pref = _pick(["300", "301", "302", "304", "305", "310", "311", "312", "313", "314", "315", "316", "317", "318", "319", "320", "321", "350", "351"], key, "pp" + salt)
    return pref + f"{_h(key, 'ph' + salt) % 10_000_000:07d}"


def _cedula(key, gender, rec, salt):
    # 10 dígitos, primer dígito 1 (rango de cédulas recientes en Colombia), lejos de cualquier original
    return "1" + f"{_h(key, 'cc' + salt) % 1_000_000_000:09d}"


def _plate(key, gender, rec, salt):
    letters = "BCDFGHJKLMNPRSTVWXYZ"
    h = _h(key, "pl" + salt)
    l3 = "".join(letters[(h >> (5 * i)) % len(letters)] for i in range(3))
    return f"{l3}{(h >> 20) % 1000:03d}"


def _passport(key, gender, rec, salt):
    return "AX" + f"{_h(key, 'pp' + salt) % 10_000_000:07d}"


def _handle(key, gender, rec, salt):
    parts = strip_accents(rec.get("name") or _name(key, gender, rec, salt)).lower().split()
    return f"{parts[0]}.{parts[-2] if len(parts) > 2 else parts[-1]}" + ("" if salt == "0" else salt)


def _address(key, gender, rec, salt):
    tipo = _pick(["Calle", "Carrera", "Transversal", "Diagonal"], key, "ad" + salt)
    h = _h(key, "ad" + salt)
    return f"{tipo} {h % 120 + 1} # {(h >> 8) % 90 + 1}-{(h >> 16) % 99 + 1}"


def _birth(key, gender, rec, salt):
    h = _h(key, "bd" + salt)
    return f"{1960 + h % 45}-{(h >> 8) % 12 + 1:02d}-{(h >> 12) % 28 + 1:02d}"


_GENERATORS = {
    "name": _name,
    "email": _email,
    "phone": _phone,
    "cedula": _cedula,
    "plate": _plate,
    "passport": _passport,
    "handle": _handle,
    "address": _address,
    "birth_iso": _birth,
}


def employee_email(registry: Registry, key: str, gender: str) -> str:
    """Correos corporativos conservan el dominio @kipupay.co."""
    with registry.lock:
        rec = registry.by_key.setdefault(key, {})
    registry.pseudonyms_for(key, gender, ("name",))
    with registry.lock:
        if "email" not in rec:
            for attempt in range(1000):
                val = _email(key, gender, rec, str(attempt), domain="kipupay.co")
                if norm(val) not in registry.used and norm(val) not in registry.forbidden:
                    registry.used.add(norm(val))
                    rec["email"] = val
                    break
        return rec["email"]


def guess_gender(first_name: str) -> str:
    """Género por nombre de pila (lista + terminación). 'x' si no se sabe."""
    f = strip_accents(first_name.split()[0]).lower() if first_name.strip() else ""
    fem = {strip_accents(n).lower() for n in NOMBRES_F}
    mas = {strip_accents(n).lower() for n in NOMBRES_M}
    if f in fem:
        return "f"
    if f in mas:
        return "m"
    if f.endswith("a") and f not in {"luca", "nicola", "andrea"}:
        return "f"
    if f.endswith(("o", "os", "el", "an", "on", "er", "es", "or")):
        return "m"
    return "x"
