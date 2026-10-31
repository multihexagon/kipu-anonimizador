FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.sh .
RUN chmod +x run.sh

# Railway inyecta $PORT. Un solo worker: el registro de personas y la corrida activa viven en un proceso.
CMD ["./run.sh"]
