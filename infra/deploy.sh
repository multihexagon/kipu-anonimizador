#!/bin/bash
# Redespliega el servicio si hay commits nuevos. Nunca interrumpe una corrida activa.
# La app escucha solo en localhost:9000; Caddy la publica con HTTPS en <ip-con-guiones>.sslip.io
# (certificado de Let's Encrypt automático). Se instala en /opt/kipu/deploy.sh y corre por cron cada 2 min.
set -euo pipefail
BRANCH="${BRANCH:-main}"
cd /opt/kipu
[ -d src/.git ] || { git clone --branch "$BRANCH" https://github.com/multihexagon/kipu-anonimizador src; FORCE=1; }
cd src
git fetch -q origin "$BRANCH"

TOKEN=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
IP=$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)
DOMAIN="${IP//./-}.sslip.io"

# Caddy (HTTPS) siempre arriba
if ! docker ps --format '{{.Names}}' | grep -q '^caddy$'; then
  docker rm -f caddy 2>/dev/null || true
  docker run -d --name caddy --restart always --network host -v caddy_data:/data caddy:2 \
    caddy reverse-proxy --from "$DOMAIN" --to localhost:9000
fi

if [ "$(git rev-parse HEAD)" = "$(git rev-parse "origin/$BRANCH")" ] && [ -z "${FORCE:-}" ] \
   && docker ps --format '{{.Names}}' | grep -q '^kipu$'; then
  exit 0
fi
if curl -fsS localhost:9000/v1/health 2>/dev/null | grep -q '"busy": *true'; then
  echo "corrida activa, posponiendo redeploy"; exit 0
fi
git reset -q --hard "origin/$BRANCH"
docker build -q -t kipu:latest .
docker rm -f kipu 2>/dev/null || true
docker run -d --name kipu --restart always -p 127.0.0.1:9000:9000 \
  -v /data:/data \
  -e DATA_DIR=/data \
  -e TEAM_NAME=kipu-anonimizador \
  -e APP_VERSION="$(git rev-parse --short HEAD)" \
  -e PSEUDO_SECRET="$(cat /opt/kipu/secret)" \
  kipu:latest
docker image prune -f >/dev/null
echo "desplegado $(git rev-parse --short HEAD) en https://$DOMAIN/v1"
