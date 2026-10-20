# Odoo 20 — projeto com melhorias próprias

- `odoo/` — código oficial do Odoo 20.0 (submódulo Git, **não editar**)
- `custom_addons/` — os nossos módulos
- `config/odoo.conf` — configuração local
- `docker-compose.yml` — PostgreSQL 17 na porta **5433**

## Primeira vez
```bash
brew install libpq openssl@3 cairo pkg-config   # psycopg2 e QR codes (rlPyCairo)
git submodule update --init --depth 1
make setup      # venv + dependências
make run        # abre http://localhost:8069
```

## Dia a dia
```bash
make help                         # lista de comandos
make run                          # arrancar (http://localhost:8069)
make update d=minhabase m=modulo  # atualizar um módulo
make test m=l10n_ao               # testes do módulo numa base nova test_l10n_ao
make lint                         # ruff + pylint-odoo
make stop                         # parar a base de dados
```

## Produção (Docker)
```bash
cp .env.example .env              # definir passwords
docker compose -f docker-compose.prod.yml up -d --build
```
Imagem: Odoo 20.0 + wkhtmltopdf 0.12.6.1 (qt patched) + `custom_addons/`. Uma base por cliente (`dbfilter = ^%d$`).

## Documentação
- `docs/PLANO-IMPLEMENTACAO.md`: plano geral e fases
- `docs/analise-legal/`: análise de conformidade (facturação, PGC, LGT, AGT)
- `docs/referencias/`: especificação AGT, OCR dos diplomas
- `docs/agt/`: processo de certificação AGT

Password mestra (gestão de bases): `admin` — mudar em `config/odoo.conf` fora de desenvolvimento.
