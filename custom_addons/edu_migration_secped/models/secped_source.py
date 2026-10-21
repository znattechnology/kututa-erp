"""Leitura da base do secPed-Express (PostgreSQL), só para leitura e limitada a uma escola."""

import psycopg2
import psycopg2.extras


class SecpedSource:
    """As linhas de cada tabela da escola, sem as apagadas (``deletedAt``). Os testes usam uma fonte em memória com
    a mesma interface: ``school`` e ``rows(table)``."""

    def __init__(self, dsn, slug):
        self.conn = psycopg2.connect(dsn)
        self.conn.set_session(readonly=True)
        self._cache = {}
        self.school = self._query('SELECT * FROM schools WHERE slug = %s', [slug])
        if not self.school:
            raise ValueError(f'Não há nenhuma escola «{slug}» no secPed.')
        self.school = self.school[0]

    def _query(self, sql, params=()):
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cr:
            cr.execute(sql, params)
            return [dict(row) for row in cr.fetchall()]

    def _columns(self, table):
        rows = self._query(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
            [table],
        )
        return {row['column_name'] for row in rows}

    def rows(self, table):
        if table not in self._cache:
            columns = self._columns(table)
            if not columns:
                raise ValueError(f'O secPed não tem a tabela {table}.')
            sql = f'SELECT * FROM "{table}" WHERE "schoolId" = %s'  # noqa: S608 (nome de tabela fixo no código)
            if 'deletedAt' in columns:
                sql += ' AND "deletedAt" IS NULL'
            self._cache[table] = self._query(sql + ' ORDER BY id', [self.school['id']])
        return self._cache[table]

    def close(self):
        self.conn.close()


class MemorySource:
    """Fonte em memória (testes): ``{'tabela': [linhas]}``."""

    def __init__(self, school, tables):
        self.school = school
        self.tables = tables

    def rows(self, table):
        return [row for row in self.tables.get(table, []) if not row.get('deletedAt')]

    def close(self):
        pass
