#!/bin/sh
# Injecta a password mestra a partir do ambiente, para não ficar no ficheiro de configuração da imagem.
set -e
CONF=/etc/odoo/odoo.conf
if [ -n "$ODOO_MASTER_PASSWORD" ]; then
    RUNTIME_CONF=/tmp/odoo.conf
    cp "$CONF" "$RUNTIME_CONF"
    printf 'admin_passwd = %s\n' "$ODOO_MASTER_PASSWORD" >> "$RUNTIME_CONF"
    CONF="$RUNTIME_CONF"
fi
exec python /opt/odoo/odoo-bin -c "$CONF" "$@"
