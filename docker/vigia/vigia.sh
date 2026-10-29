#!/bin/bash
# Vigia da VPS: corre de 5 em 5 minutos no cron e manda um ping ao Healthchecks.io.
#   tudo bem       -> ping simples
#   algum problema -> /fail com a lista dos problemas (o Healthchecks avisa por e-mail)
#   VPS em baixo   -> o ping não chega e o Healthchecks avisa ao fim do período de tolerância
#
# Uso (cron do anfitrião):
#   */5 * * * *  /opt/kututa/app/docker/vigia/vigia.sh >> /opt/kututa/vigia.log 2>&1
#
# Configuração em $HC_ENV (chmod 600), ver healthchecks.env.example.
set -uo pipefail

HC_ENV=${HC_ENV:-/opt/kututa/healthchecks.env}
# shellcheck disable=SC1090
source "$HC_ENV"
: "${HC_VIGIA:?}"
SITES=${SITES:-https://kututa.ao/web/login https://vovoeva.kututa.ao/web/login https://lbdf.kututa.ao/web/login https://labtic.online/entrar}
CONTAINERS=${CONTAINERS:-app-odoo-1 app-db-1 proxy-caddy-1}
DISCO_MAX=${DISCO_MAX:-85}
RAM_MIN_MB=${RAM_MIN_MB:-300}
CERT_DIAS=${CERT_DIAS:-14}
COPIA_MAX_HORAS=${COPIA_MAX_HORAS:-26}
COPIA_OK=${COPIA_OK:-/opt/kututa/copias/ultima-copia-ok}

PROBLEMAS=()

for URL in $SITES; do
    CODIGO=$(curl -s -o /dev/null -m 20 -w '%{http_code}' "$URL")
    [ "$CODIGO" = 200 ] || PROBLEMAS+=("$URL respondeu $CODIGO")
    HOST=${URL#https://}; HOST=${HOST%%/*}
    FIM=$(echo | openssl s_client -connect "$HOST:443" -servername "$HOST" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
    if [ -n "$FIM" ]; then
        DIAS=$(( ($(date -d "$FIM" +%s) - $(date +%s)) / 86400 ))
        [ "$DIAS" -ge "$CERT_DIAS" ] || PROBLEMAS+=("certificado de $HOST expira em $DIAS dias")
    fi
done

for C in $CONTAINERS; do
    ESTADO=$(docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' "$C" 2>/dev/null) || ESTADO=ausente
    case "$ESTADO" in running|running/healthy) ;; *) PROBLEMAS+=("container $C: $ESTADO") ;; esac
done

DISCO=$(df --output=pcent / | tail -1 | tr -dc 0-9)
[ "$DISCO" -lt "$DISCO_MAX" ] || PROBLEMAS+=("disco a ${DISCO}%")

RAM=$(free -m | awk '/^Mem:/ {print $7}')
[ "$RAM" -ge "$RAM_MIN_MB" ] || PROBLEMAS+=("só ${RAM} MB de RAM disponível")

if [ -f "$COPIA_OK" ]; then
    HORAS=$(( ($(date +%s) - $(date -d "$(cat "$COPIA_OK")" +%s)) / 3600 ))
    [ "$HORAS" -lt "$COPIA_MAX_HORAS" ] || PROBLEMAS+=("última cópia de segurança há ${HORAS} h")
else
    PROBLEMAS+=("nenhuma cópia de segurança registada")
fi

if [ ${#PROBLEMAS[@]} -eq 0 ]; then
    curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "ok: disco ${DISCO}%, RAM livre ${RAM} MB" "$HC_VIGIA"
else
    MSG=$(printf '%s\n' "${PROBLEMAS[@]}")
    echo "$(date -u +%FT%TZ) $MSG"
    curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "$MSG" "$HC_VIGIA/fail"
fi
