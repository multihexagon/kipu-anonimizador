import os
import tempfile
from pathlib import Path

os.environ.setdefault("PSEUDO_SECRET", "test-secret")

from app.detectors import find_formatted  # noqa: E402
from app.pseudonyms import Registry, guess_gender  # noqa: E402
from app.textnorm import norm, norm_loose  # noqa: E402


def test_norm_tolera_tildes_mayusculas_invisibles():
    assert norm("LUCÍA​  FERRER") == norm("lucia ferrer")
    assert norm_loose("L u c i a-Ferrer") == norm_loose("LUCIA FERRER")


def test_seudonimo_determinista_y_congelado():
    d = Path(tempfile.mkdtemp())
    r1 = Registry(d / "reg.json")
    a = r1.pseudonyms_for("CL-1", "f", ("name", "email", "cedula", "phone"))
    r1.save()
    # mismo secreto, disco perdido → mismo resultado
    r2 = Registry(None)
    b = r2.pseudonyms_for("CL-1", "f", ("name", "email", "cedula", "phone"))
    assert a == b
    # disco presente → congelado aunque llegue antes una persona nueva
    r3 = Registry(d / "reg.json")
    r3.pseudonyms_for("CL-NUEVA", "f", ("name",))
    assert r3.pseudonyms_for("CL-1", "f", ("name",))["name"] == a["name"]


def test_unicidad_y_formatos():
    r = Registry(None)
    names = {r.pseudonyms_for(f"CL-{i}", "f", ("name",))["name"] for i in range(500)}
    assert len(names) == 500
    p = r.pseudonyms_for("CL-1", "m", ("cedula", "phone", "plate"))
    assert len(p["cedula"]) == 10 and p["cedula"].isdigit()
    assert len(p["phone"]) == 10 and p["phone"].startswith("3")
    assert len(p["plate"]) == 6


def test_no_entrega_nombres_reales():
    r = Registry(None)
    first = r.pseudonyms_for("X", "f", ("name",))["name"]
    r2 = Registry(None)
    r2.forbid([first])
    assert r2.pseudonyms_for("X", "f", ("name",))["name"] != first


def test_genero():
    assert guess_gender("María José") == "f"
    assert guess_gender("Hernán") == "m"


def test_detectores():
    t = "escríbeme a lucia ferrer arroba gmail punto com o al 310 555 1234, cc 1.020.304.050, placa ABC-123, <@U0V6WYVYG>"
    kinds = {k: v for _, _, k, v in find_formatted(t)}
    assert kinds["email_spoken"] == "lucia.ferrer@gmail.com"
    assert kinds["phone"] == "3105551234"
    assert kinds["cedula"] == "1020304050"
    assert kinds["plate"] == "ABC123"
    assert kinds["mention"] == "U0V6WYVYG"
