VENV := .venv
PY   := $(VENV)/bin/python
ODOO := $(PY) odoo/odoo-bin -c config/odoo.conf
LIBPQ := $(shell brew --prefix libpq 2>/dev/null)
SSL   := $(shell brew --prefix openssl@3 2>/dev/null)
DB_CONTAINER := odoo20-db
ADDONS := custom_addons
comma := ,
empty :=
space := $(empty) $(empty)

.PHONY: help setup db run shell update test lint stop

help:             ## Lista os comandos disponíveis
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

setup:            ## (requer: brew install libpq openssl@3 cairo pkg-config) Cria o venv e instala as dependências
	python3.13 -m venv $(VENV)
	$(VENV)/bin/pip install -U pip wheel
	PATH="$(LIBPQ)/bin:$$PATH" LDFLAGS="-L$(SSL)/lib" $(VENV)/bin/pip install -r odoo/requirements.txt
	PKG_CONFIG_PATH="$(shell brew --prefix 2>/dev/null)/lib/pkgconfig" $(VENV)/bin/pip install -r requirements-dev.txt
	$(VENV)/bin/pre-commit install

db:               ## Arranca o PostgreSQL (Docker)
	docker compose up -d db

stop:             ## Pára o PostgreSQL
	docker compose stop db

run: db           ## Arranca o Odoo em http://localhost:8069
	$(ODOO)

shell: db         ## Shell Odoo:  make shell d=<base>
	$(ODOO) shell -d $(d)

update: db        ## Atualiza módulo:  make update d=<base> m=<modulo>
	$(ODOO) -d $(d) -u $(m) --stop-after-init

test: db          ## Testa módulo numa base nova test_<modulo>:  make test m=<modulo>[,<modulo2>] [t=<test_tags>]
	@test -n "$(m)" || (echo "Indique o módulo: make test m=<modulo>"; exit 1)
	$(eval TDB := test_$(firstword $(subst $(comma), ,$(m))))
	docker exec $(DB_CONTAINER) dropdb -U odoo --force --if-exists $(TDB)
	rm -rf .local/filestore/filestore/$(TDB)
	$(ODOO) -d $(TDB) -i $(m) --without-demo --test-enable \
		--test-tags=$(if $(t),$(t),$(subst $(space),$(comma),$(foreach x,$(subst $(comma), ,$(m)),/$(x)))) \
		--stop-after-init --no-http --http-port=8169 --log-level=test

lint:             ## Lint dos módulos próprios (ruff + pylint-odoo)
	$(VENV)/bin/ruff check $(ADDONS) tools
	$(VENV)/bin/pylint --rcfile=.pylintrc --disable=manifest-required-author,manifest-deprecated-key,missing-readme $(ADDONS)/*/
