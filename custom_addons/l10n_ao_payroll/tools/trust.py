"""Escritas internas do processamento salarial (cálculo, fecho e anulação da folha).

O cliente controla o contexto das chamadas RPC, por isso as excepções às regras marcam-se no cursor do servidor:
«with trusted(env): ...» e, nas regras, «is_trusted(env)».
"""

from contextlib import contextmanager

TRUSTED = '_l10n_ao_payroll_trusted'


@contextmanager
def trusted(env):
    previous = getattr(env.cr, TRUSTED, 0)
    setattr(env.cr, TRUSTED, previous + 1)
    try:
        yield
    finally:
        setattr(env.cr, TRUSTED, previous)


def is_trusted(env):
    return env.su or getattr(env.cr, TRUSTED, 0) > 0
