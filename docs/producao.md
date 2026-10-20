# Produção (Docker)

`docker-compose.prod.yml` sobe **Odoo + PostgreSQL**. É genérico: serve para alojamento próprio (SaaS) ou para instalação no cliente.

## Arranque
```bash
cp .env.example .env            # DB_USER, DB_PASSWORD, ODOO_MASTER_PASSWORD
docker compose -f docker-compose.prod.yml up -d --build
```
- As credenciais da base passam por variáveis de ambiente (`PGHOST`, `PGUSER`, `PGPASSWORD`), lidas pelo Odoo. Nunca vão na linha de comando (ficariam visíveis em `ps`).
- A password mestra (`ODOO_MASTER_PASSWORD`) é injectada no `odoo.conf` em runtime por `docker/entrypoint.sh`.
- O Odoo arranca só depois do healthcheck do PostgreSQL.

## Reverse proxy: obrigatório
O Odoo corre em modo multi-worker (`workers = 4`), por isso o **websocket** (chat, notificações, bus) é servido numa porta própria (**8072**). As portas 8069 e 8072 ficam expostas **só em 127.0.0.1**; o acesso público faz-se por um reverse proxy com TLS:

| Pedido | Destino |
|---|---|
| `/websocket` | `127.0.0.1:8072` |
| tudo o resto | `127.0.0.1:8069` |

`proxy_mode = True` já está activo no `docker/odoo.conf`: o Odoo confia nos cabeçalhos `X-Forwarded-*` do proxy. **Sem proxy** não há TLS nem websocket, e o `proxy_mode` deve ser desligado.

Exemplo com Caddy (`Caddyfile`):
```
erp.exemplo.ao {
    @websocket path /websocket
    reverse_proxy @websocket 127.0.0.1:8072
    reverse_proxy 127.0.0.1:8069
}
```

## Uma base por cliente
`dbfilter = ^%d$` escolhe a base pelo subdomínio (`cliente1.erp.exemplo.ao` → base `cliente1`). O gestor de bases está desligado (`list_db = False`); as bases criam-se por CLI:
```bash
docker compose -f docker-compose.prod.yml exec odoo /usr/local/bin/entrypoint.sh \
    -d cliente1 -i account,l10n_ao --load-language=pt_PT --stop-after-init
```

## Imagem
- `python:3.13-slim` + Odoo 20.0 (`odoo/`) + `custom_addons/` + wkhtmltopdf 0.12.6.1 (qt patched, amd64 e arm64).
- As dependências de compilação são removidas depois do `pip install`.
- O código e a configuração pertencem ao `root` (só leitura); o processo corre como `odoo` e só escreve em `/var/lib/odoo`.
- `HEALTHCHECK` em `/web/health`.

## Pendente
- Verificação do checksum do `.deb` do wkhtmltopdf no build.
- Cópias de segurança automáticas (`pg_dump` + filestore).
- Utilizador PostgreSQL dedicado sem privilégios de superuser (hoje o Odoo usa o `POSTGRES_USER`).
