# Kipu anonimizador

Servicio HTTP para el reto Frontier "Vende los datos sin vender a la gente": anonimiza el corpus de soporte de Kipu Pay con seudónimos consistentes.

## Endpoints (`/v1`)

| Método y ruta | Qué hace |
| --- | --- |
| `GET /health` | `{status, team, version, models}` |
| `POST /run` | `{sources_url, token}` → regenera `output/` en segundo plano, devuelve `job_id` (idempotente) |
| `GET /run/{job_id}` | `queued` / `running` / `done` / `failed`, conteos y costo |
| `GET /output/{archivo}` | `chats.jsonl`, `docs.jsonl`, `tables.jsonl`, `entities.json` de la última corrida terminada |
| `POST /anonymize` | `{source, records}` (≤ 50) → mismos ids anonimizados + entidades |
| `GET /entities` | diccionario completo de la última corrida |

## Correr local

```bash
pip install -r requirements.txt
./run.sh            # http://localhost:9000/v1/health
```

## Variables de entorno

| Variable | Para qué |
| --- | --- |
| `DATA_DIR` | carpeta persistente (en Railway: volumen montado en `/data`) |
| `PSEUDO_SECRET` | clave secreta de los seudónimos. **Nunca cambiarla entre corridas.** |
| `ANONYMIZE_READY` | `1` habilita `/anonymize`; mientras no, responde 503 para no gastar corridas de evaluación |
| `TEAM_NAME`, `APP_VERSION`, `LLM_MODELS` | lo que reporta `/health` |

Los datos del reto y las salidas nunca se versionan (ver `.gitignore`): contienen datos personales reales.
