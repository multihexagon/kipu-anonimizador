#!/bin/sh
# Levanta el servicio. Local: ./run.sh  → http://localhost:9000/v1/health
set -e
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-9000}" --workers 1
