"""Migra uma escola do secPed-Express para uma base do Kututa ERP. Corre dentro do ``odoo-bin shell``:

    SECPED_DSN=postgresql://utilizador:palavra-passe@localhost:5432/secped_dev \\
    SECPED_SAIDA=/caminho/fora/do/repositorio \\
        .venv/bin/python odoo/odoo-bin shell -c config/odoo.conf -d <base> --no-http < tools/migrar_secped.py

Variáveis:
* ``SECPED_DSN`` (obrigatória): ligação à base do secPed, só para leitura;
* ``SECPED_ESCOLA``: o ``slug`` da escola no secPed (por omissão ``vovo-eva``);
* ``SECPED_FASES``: fases separadas por vírgulas (por omissão, todas);
* ``SECPED_ENSAIO=1``: corre tudo e desfaz no fim (nada fica gravado);
* ``SECPED_SAIDA``: directório para ``avisos.csv`` e ``pauta-diferente.csv``. Têm nomes e notas de alunos: nunca
  dentro do repositório.

Sem ensaio, cada fase é gravada ao terminar: se uma falhar, corrige-se e volta-se a correr (a migração é idempotente).
"""

import csv
import json
import os
import pathlib
from urllib.parse import urlsplit, urlunsplit

from odoo.addons.edu_migration_secped.models.edu_migration_secped import PHASES
from odoo.addons.edu_migration_secped.models.secped_source import SecpedSource

dsn = os.environ['SECPED_DSN']
dsn = urlunsplit(urlsplit(dsn)._replace(query=''))  # o Prisma acrescenta ?schema=…, que o psycopg2 recusa
slug = os.environ.get('SECPED_ESCOLA', 'vovo-eva')
phases = tuple(p.strip() for p in os.environ.get('SECPED_FASES', ','.join(PHASES)).split(',') if p.strip())
dry_run = os.environ.get('SECPED_ENSAIO') == '1'
output = os.environ.get('SECPED_SAIDA')

source = SecpedSource(dsn, slug)
try:
    report = env['edu.migration.secped']._run(  # noqa: F821 (env do odoo-bin shell)
        source,
        phases=phases,
        commit=None if dry_run else env.cr.commit,  # noqa: F821
    )
finally:
    source.close()
if dry_run:
    env.cr.rollback()  # noqa: F821
else:
    env.cr.commit()  # noqa: F821

kinds = {}
for kind, _detail in report['issues']:
    kinds[kind] = kinds.get(kind, 0) + 1
summary = {
    'ensaio': dry_run,
    'registos': report['counts'],
    'indicadores': report['metrics'],
    'avisos_por_tipo': kinds,
}
print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
if output:
    folder = pathlib.Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'avisos.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['tipo', 'aviso'])
        writer.writerows(report['issues'])
    with (folder / 'pauta-diferente.csv').open('w', newline='', encoding='utf-8') as handle:
        fields = ['matricula', 'disciplina', 'cf', 'pg', 'bonificacao', 'secped', 'odoo']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report['mismatches'])
    print(f'Relatório em {folder}')
