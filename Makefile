VENV := .venv
PY   := $(VENV)/bin/python
ODOO := $(PY) odoo/odoo-bin -c config/odoo.conf
LIBPQ := $(shell brew --prefix libpq 2>/dev/null)
SSL   := $(shell brew --prefix openssl@3 2>/dev/null)

.PHONY: setup db run shell update test stop

setup:            ## (requer: brew install libpq) Cria o venv e instala as dependências
	python3.13 -m venv $(VENV)
	$(VENV)/bin/pip install -U pip wheel
	PATH="$(LIBPQ)/bin:$$PATH" LDFLAGS="-L$(SSL)/lib" $(VENV)/bin/pip install -r odoo/requirements.txt

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

test: db          ## Testa módulo:  make test d=<base> m=<modulo>
	$(ODOO) -d $(d) -u $(m) --test-enable --stop-after-init
