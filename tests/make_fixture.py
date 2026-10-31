"""Crea un mini dataset SINTÉTICO (personas inventadas) con la estructura de sample/input.

Sirve para probar descarga + normalización sin depender del API de fuentes.
Uso: python tests/make_fixture.py tests/fixture
"""
import io
import json
import sys
from pathlib import Path

from pypdf import PdfWriter

root = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixture")
(root / "chats" / "soporte-cobros").mkdir(parents=True, exist_ok=True)
(root / "docs").mkdir(parents=True, exist_ok=True)
(root / "tables").mkdir(parents=True, exist_ok=True)

users = [
    {"id": "UCLI1", "name": "lucia", "real_name": "Lucía Ferrer", "profile": {"real_name": "Lucía Ferrer"}},
    {"id": "UAGT1", "name": "tomas", "real_name": "Tomás Ibarra", "profile": {"real_name": "Tomás Ibarra", "title": "Agente", "email": "tomas.ibarra@kipupay.co"}},
]
channels = [{"id": "C1", "name": "soporte-cobros", "purpose": "cobros", "members": ["UCLI1", "UAGT1"]}]
msgs = [
    {"type": "message", "user": "UCLI1", "text": "Hola, soy Lucía Ferrer, mi correo es lucia ferrer arroba gmail punto com", "ts": "100.0001", "client_msg_id": "m1", "files": [{"id": "F1", "name": "extracto_LUCIA_FERRER.pdf"}]},
    {"type": "message", "user": "UAGT1", "text": "Hola <@UCLI1>, ya reviso tu caso CL-00001", "ts": "100.0002", "thread_ts": "100.0001", "client_msg_id": "m2"},
]
(root / "chats" / "users.json").write_text(json.dumps(users, ensure_ascii=False))
(root / "chats" / "channels.json").write_text(json.dumps(channels))
(root / "chats" / "soporte-cobros" / "2026-09-14.json").write_text(json.dumps(msgs, ensure_ascii=False))

w = PdfWriter()
w.add_blank_page(width=200, height=200)
w.add_metadata({"/Author": "Tomás Ibarra", "/Subject": "Política de cobro", "/Title": "Política"})
buf = io.BytesIO(); w.write(buf)
(root / "docs" / "politica.pdf").write_bytes(buf.getvalue())
(root / "docs" / "organigrama.html").write_text(
    '<html><head><title>Organigrama</title><meta name="author" content="Tomás Ibarra"></head>'
    "<body><h1>Equipo</h1><p>Líder: Tomás Ibarra</p><!-- revisar con Lucía Ferrer --></body></html>", encoding="utf-8")
(root / "docs" / "notas.md").write_text("---\ntitle: Notas\nauthor: tomas.ibarra@kipupay.co\n---\n# Notas\nPreparado por Tomás Ibarra.\n", encoding="utf-8")
(root / "docs" / "index.json").write_text(json.dumps([
    {"id": "doc_01", "filename": "politica.pdf", "format": "pdf"},
    {"id": "doc_02", "filename": "organigrama.html", "format": "html"},
    {"id": "doc_03", "filename": "notas.md", "format": "md"},
]))

(root / "tables" / "clientes.csv").write_bytes(
    "cliente_id;nombre;cedula;ocupacion;barrio\nCL-00001;Lucía Ferrer;1020304050;periodista;Laureles\n".encode("latin-1"))
(root / "tables" / "transacciones.csv").write_text("tx_id,cliente_id,monto\nTX-000001,CL-00001,150000\n", encoding="utf-8")
(root / "tables" / "pqrs.xml").write_text("<pqrs><pqr id=\"PQR-2026-0001\"><cliente_id>CL-00001</cliente_id><detalle>Cobro doble</detalle></pqr></pqrs>", encoding="utf-8")
(root / "tables" / "empleados.xml").write_text("<empleados><empleado><codigo>KP-001</codigo><nombre>Tomás Ibarra</nombre><reporta_a></reporta_a></empleado></empleados>", encoding="utf-8")

(root / "record_index.json").write_text(json.dumps({
    "chats": ["m1", "m2"],
    "docs": ["doc_01", "doc_02", "doc_03"],
    "tables": ["clientes:CL-00001", "transacciones:TX-000001", "pqrs:PQR-2026-0001", "empleados:KP-001"],
}))
print("fixture en", root)
