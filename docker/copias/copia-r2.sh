#!/bin/bash
# Cópia de segurança diária de todas as bases do Kututa para o Cloudflare R2.
#
# Por base: pg_dump (formato custom) + filestore (anexos, imagens do site, PDFs).
# Fica no R2 em <bucket>/diario/<data>/ durante RETENCAO_DIARIA dias; a cópia do
# dia 1 de cada mês vai também para <bucket>/mensal/<data>/ e fica RETENCAO_MENSAL dias.
# Localmente guardam-se só as últimas RETENCAO_LOCAL cópias (servem para restaurar depressa).
#
# Uso (cron do anfitrião, a partir da pasta do compose):
#   30 2 * * *  /opt/kututa/app/docker/copias/copia-r2.sh >> /opt/kututa/copias/copias.log 2>&1
#
# Credenciais em $CONFIG (chmod 600), ver r2.env.example. O token do R2 só precisa de
# «Object Read & Write» no bucket das cópias.
set -euo pipefail
umask 077

APP_DIR=${APP_DIR:-/opt/kututa/app}
DESTINO=${DESTINO:-/opt/kututa/copias}
CONFIG=${CONFIG:-$DESTINO/r2.env}
RCLONE_IMAGE=${RCLONE_IMAGE:-rclone/rclone:1.68.2}

# shellcheck disable=SC1090
source "$CONFIG"
: "${R2_ACCOUNT_ID:?}" "${R2_ACCESS_KEY_ID:?}" "${R2_SECRET_ACCESS_KEY:?}" "${R2_BUCKET:?}"
RETENCAO_DIARIA=${RETENCAO_DIARIA:-30}
RETENCAO_MENSAL=${RETENCAO_MENSAL:-365}
RETENCAO_LOCAL=${RETENCAO_LOCAL:-3}

# Healthchecks.io (opcional): /start no início, /fail se algo falhar, ping simples no fim.
# Se o ping de sucesso não chegar a horas, é o Healthchecks que avisa (também quando a VPS está em baixo).
HC_ENV=${HC_ENV:-/opt/kututa/healthchecks.env}
# shellcheck disable=SC1090
[ -f "$HC_ENV" ] && source "$HC_ENV"
hc() {
    [ -n "${HC_COPIAS:-}" ] || return 0
    curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "${2:-}" "$HC_COPIAS$1" || true
}
trap 'hc /fail "copia-r2.sh falhou na linha $LINENO (ver /opt/kututa/copias/copias.log)"' ERR
hc /start

DATA=$(date -u +%Y-%m-%d-%H%M)
PASTA=$DESTINO/local/$DATA
mkdir -p "$PASTA"
cd "$APP_DIR"
compose() { docker compose -f docker-compose.prod.yml "$@"; }

echo "== $(date -u +%FT%TZ) início $DATA"

BASES=$(compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d postgres -Atc "select datname from pg_database where not datistemplate and datname <> '"'"'postgres'"'"' order by 1"')
[ -n "$BASES" ] || { echo "ERRO: nenhuma base encontrada"; exit 1; }

for BASE in $BASES; do
    compose exec -T db sh -c "pg_dump -U \"\$POSTGRES_USER\" -d '$BASE' -Fc" > "$PASTA/$BASE.dump"
    # Um dump que o pg_restore não lê não é uma cópia: falhar já, não no dia do restauro.
    compose exec -T db pg_restore -l < "$PASTA/$BASE.dump" > /dev/null
    if compose exec -T odoo test -d "/var/lib/odoo/filestore/$BASE"; then
        compose exec -T odoo tar -C /var/lib/odoo/filestore -czf - "$BASE" > "$PASTA/$BASE-filestore.tar.gz"
    fi
    echo "   $BASE: $(du -h "$PASTA/$BASE.dump" | cut -f1) base, $(du -h "$PASTA/$BASE-filestore.tar.gz" 2>/dev/null | cut -f1 || echo 0) ficheiros"
done
(cd "$PASTA" && sha256sum -- * > SHA256SUMS)

# As chaves vão num ficheiro (umask 077) e não com -e, para não aparecerem no «ps» do anfitrião.
RCLONE_ENV=$(mktemp "$DESTINO/.rclone.XXXXXX")
trap 'rm -f "$RCLONE_ENV"' EXIT
cat > "$RCLONE_ENV" <<FIM
RCLONE_CONFIG=/dev/null
RCLONE_CONFIG_R2_TYPE=s3
RCLONE_CONFIG_R2_PROVIDER=Cloudflare
RCLONE_CONFIG_R2_ACCESS_KEY_ID=$R2_ACCESS_KEY_ID
RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=$R2_SECRET_ACCESS_KEY
RCLONE_CONFIG_R2_ENDPOINT=https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com
RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
FIM
rclone() {
    docker run --rm -v "$DESTINO/local:/copias:ro" --env-file "$RCLONE_ENV" \
        "$RCLONE_IMAGE" --contimeout 30s --timeout 5m --retries 3 --low-level-retries 3 "$@"
}

rclone copy "/copias/$DATA" "r2:$R2_BUCKET/diario/$DATA" --checksum
rclone check "/copias/$DATA" "r2:$R2_BUCKET/diario/$DATA" --one-way
if [ "$(date -u +%d)" = "01" ]; then
    rclone copy "/copias/$DATA" "r2:$R2_BUCKET/mensal/$DATA" --checksum
fi

rclone delete "r2:$R2_BUCKET/diario" --min-age "${RETENCAO_DIARIA}d" --rmdirs
rclone delete "r2:$R2_BUCKET/mensal" --min-age "${RETENCAO_MENSAL}d" --rmdirs

# Locais: ficam as RETENCAO_LOCAL mais recentes.
ls -1d "$DESTINO"/local/*/ | sort | head -n -"$RETENCAO_LOCAL" | xargs -r rm -rf

date -u +%FT%TZ > "$DESTINO/ultima-copia-ok"
echo "== $(date -u +%FT%TZ) fim $DATA"
hc "" "$DATA: $(echo $BASES) — $(du -sh "$PASTA" | cut -f1) em r2:$R2_BUCKET/diario/$DATA"
