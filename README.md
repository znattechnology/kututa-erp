# Odoo 20 — projeto com melhorias próprias

- `odoo/` — código oficial do Odoo 20.0 (submódulo Git, **não editar**)
- `custom_addons/` — os nossos módulos
- `config/odoo.conf` — configuração local
- `docker-compose.yml` — PostgreSQL 17 na porta **5433**

## Primeira vez
```bash
brew install libpq openssl@3   # para compilar o psycopg2
git submodule update --init --depth 1
make setup      # venv + dependências
make run        # abre http://localhost:8069
```

## Dia a dia
```bash
make run                          # arrancar
make update d=minhabase m=modulo  # atualizar um módulo
make test   d=minhabase m=modulo  # correr testes
make stop                         # parar a base de dados
```

Password mestra (gestão de bases): `admin` — mudar em `config/odoo.conf` fora de desenvolvimento.
