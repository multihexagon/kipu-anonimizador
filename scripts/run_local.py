"""Corre el pipeline contra una carpeta local (p. ej. sample/input) y escribe la salida.

Uso:
  python scripts/run_local.py sample/input output/ [--record-index sample/record_index.json]
Luego:
  node validar.mjs output/ --public sample
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline import run_from_source  # noqa: E402
from app.sources import DirSource  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("input_dir")
ap.add_argument("out_dir")
ap.add_argument("--record-index")
a = ap.parse_args()

t0 = time.time()
res = run_from_source(DirSource(a.input_dir, a.record_index), Path(a.out_dir))
print(json.dumps({**res, "seconds": round(time.time() - t0, 2)}, ensure_ascii=False))
