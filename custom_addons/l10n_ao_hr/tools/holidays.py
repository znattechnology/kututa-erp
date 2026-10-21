"""Feriados nacionais de Angola: Lei n.º 10/11, de 16 de Fevereiro, na redacção da Lei n.º 11/18, de 28 de Setembro.

Art. 2.º: os 12 feriados (10 fixos e 2 móveis, Carnaval e Sexta-feira Santa).
Art. 6.º: ponte, quando o feriado cai a uma terça-feira (segunda-feira anterior) ou a uma quinta-feira
(sexta-feira seguinte). Um feriado ao fim-de-semana não se transfere.
Art. 6.º, n.º 3: na semana anterior à ponte acresce 1h30 por dia ao período normal (não é gerado aqui).
Art. 7.º, n.º 2: 24 e 31 de Dezembro, a partir das 12h30 (só nos dias que não são já feriado ou ponte).
"""

from datetime import date, timedelta

FIXED_HOLIDAYS = [
    (1, 1, 'Dia do Ano Novo'),
    (2, 4, 'Dia do Início da Luta Armada de Libertação Nacional'),
    (3, 8, 'Dia Internacional da Mulher'),
    (3, 23, 'Dia da Libertação da África Austral'),
    (4, 4, 'Dia da Paz e da Reconciliação Nacional'),
    (5, 1, 'Dia Internacional do Trabalhador'),
    (9, 17, 'Dia do Fundador da Nação e do Herói Nacional'),
    (11, 2, 'Dia dos Finados'),
    (11, 11, 'Dia da Independência Nacional'),
    (12, 25, 'Dia de Natal e da Família'),
]
HALF_DAYS = [(12, 24, 'Véspera de Natal'), (12, 31, 'Véspera de Ano Novo')]
HALF_DAY_START = 12.5


def easter(year):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(year, month, day + 1)


def _holidays_of(year):
    easter_sunday = easter(year)
    holidays = [(date(year, month, day), name) for month, day, name in FIXED_HOLIDAYS]
    holidays.append((easter_sunday - timedelta(days=47), 'Dia do Carnaval'))
    holidays.append((easter_sunday - timedelta(days=2), 'Sexta-feira Santa'))
    return holidays


def public_holidays(year):
    """[(data, nome, é ponte)] dos dias do ano, por ordem de data.

    Inclui as pontes de feriados do ano seguinte que caem neste ano (1 de Janeiro a uma terça-feira dá
    ponte a 31 de Dezembro) e exclui as pontes deste ano que caem no anterior.
    """
    holidays = _holidays_of(year - 1) + _holidays_of(year) + _holidays_of(year + 1)
    result = {day: (name, False) for day, name in holidays}
    for day, name in holidays:
        if day.weekday() == 1:  # terça-feira
            bridge = day - timedelta(days=1)
        elif day.weekday() == 3:  # quinta-feira
            bridge = day + timedelta(days=1)
        else:
            continue
        result.setdefault(bridge, (f'Ponte: {name}', True))
    return [(day, name, bridge) for day, (name, bridge) in sorted(result.items()) if day.year == year]


def half_days(year):
    """[(data, nome)] das tardes de 24 e 31 de Dezembro que não são já feriado ou ponte."""
    full = {day for day, _name, _bridge in public_holidays(year)}
    return [
        (date(year, month, day), name)
        for month, day, name in HALF_DAYS
        if date(year, month, day) not in full and date(year, month, day).weekday() < 5
    ]


def is_public_holiday(day):
    return any(holiday == day for holiday, _name, _bridge in public_holidays(day.year))
