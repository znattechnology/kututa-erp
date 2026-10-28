#!/bin/sh
# Injecta a password mestra a partir do ambiente, para não ficar no ficheiro de configuração da imagem.
set -e
umask 077
CONF=/etc/odoo/odoo.conf
if [ -z "$ODOO_MASTER_PASSWORD" ]; then
    # Sem a password mestra definida, o Odoo usaria «admin»: não arranca.
    echo "ODOO_MASTER_PASSWORD não está definida (ver .env.example)." >&2
    exit 1
fi
RUNTIME_CONF=/tmp/odoo.conf
cp "$CONF" "$RUNTIME_CONF"
# Guardada em hash (pbkdf2), como o Odoo a escreve no gestor de bases.
HASH=$(python -c 'import os; from passlib.context import CryptContext; print(CryptContext(["pbkdf2_sha512"]).hash(os.environ["ODOO_MASTER_PASSWORD"]))')
printf 'admin_passwd = %s\n' "$HASH" >> "$RUNTIME_CONF"
exec python /opt/odoo/odoo-bin -c "$RUNTIME_CONF" "$@"
