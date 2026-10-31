"""Normalización tolerante para COMPARAR formas (no para escribir salida).

El barrido del jurado tolera confusables, separadores e invisibles; la detección también debe tolerarlos.
"""
from __future__ import annotations

import re
import unicodedata

_INVISIBLES = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_CONFUSABLES = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a"})


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s: str) -> str:
    """Forma canónica de un nombre: NFKC, sin invisibles, sin tildes, minúsculas, espacios simples."""
    s = unicodedata.normalize("NFKC", s).translate(_INVISIBLES)
    s = strip_accents(s).casefold()
    s = re.sub(r"[^\w@.+-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_loose(s: str) -> str:
    """Más agresiva: además colapsa confusables y quita todo separador. Útil para el barrido de fugas."""
    return re.sub(r"[\W_]+", "", norm(s).translate(_CONFUSABLES))


def digits(s: str) -> str:
    return re.sub(r"\D", "", s)
