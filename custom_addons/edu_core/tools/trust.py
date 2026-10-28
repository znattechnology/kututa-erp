"""Escritas internas dos módulos escolares.

O cliente controla o contexto de qualquer chamada RPC, por isso uma flag de contexto não pode abrir excepções às
regras (estados, aprovações, notas). As escritas feitas pelo próprio código marcam-se no cursor do servidor, onde o
cliente não chega: «with trusted(env): ...» e, nas regras, «is_trusted(env)».
"""

from contextlib import contextmanager

TRUSTED = '_edu_trusted'


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


def is_marked(env):
    """Só a marca do servidor (sem contar o sudo): para as regras que também valem em sudo."""
    return getattr(env.cr, TRUSTED, 0) > 0
