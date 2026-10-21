"""Números, notas, classes e datas por extenso em português (norma de Angola e Portugal: catorze, dezasseis,
dezassete, dezanove), como nos documentos oficiais das escolas."""

from odoo.addons.edu_evaluation.tools.grading import round_units

UNITS = [
    'zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez', 'onze', 'doze', 'treze',
    'catorze', 'quinze', 'dezasseis', 'dezassete', 'dezoito', 'dezanove',
]  # fmt: skip
TENS = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
HUNDREDS = [
    '', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos',
    'novecentos',
]  # fmt: skip
ORDINAL_UNITS = ['', 'Primeira', 'Segunda', 'Terceira', 'Quarta', 'Quinta', 'Sexta', 'Sétima', 'Oitava', 'Nona']
MONTHS = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro',
    'Dezembro',
]  # fmt: skip


def number_words(number):  # noqa: PLR0911 (casos do português)
    """Inteiro de 0 a 999 999 por extenso."""
    number = int(number)
    if number < 0:
        return 'menos ' + number_words(-number)
    if number < 20:
        return UNITS[number]
    if number < 100:
        tens, unit = divmod(number, 10)
        return TENS[tens] + (f' e {UNITS[unit]}' if unit else '')
    if number == 100:
        return 'cem'
    if number < 1000:
        hundreds, rest = divmod(number, 100)
        return HUNDREDS[hundreds] + (f' e {number_words(rest)}' if rest else '')
    thousands, rest = divmod(number, 1000)
    head = 'mil' if thousands == 1 else f'{number_words(thousands)} mil'
    if not rest:
        return head
    joiner = ' e ' if rest < 100 or rest % 100 == 0 else ' '
    return head + joiner + number_words(rest)


def grade_number(value):
    """Nota inteira com dois dígitos: 8 → «08»."""
    return f'{round_units(value or 0):02d}'


def grade_text(value, style='upper'):
    """«15 (QUINZE) VALORES» (upper) ou «13 (Treze) Valores» (title); 1 valor no singular."""
    number = round_units(value or 0)
    words = number_words(number)
    unit = 'valor' if number == 1 else 'valores'
    if style == 'title':
        return f'{grade_number(number)} ({words.capitalize()}) {unit.capitalize()}'
    return f'{grade_number(number)} ({words.upper()}) {unit.upper()}'


def ordinal_feminine(number):
    """1 → «Primeira», 12 → «Décima Segunda» (classes)."""
    number = int(number)
    if number <= 0:
        return 'Iniciação'
    tens, unit = divmod(number, 10)
    parts = []
    if tens == 1:
        parts.append('Décima')
    elif tens == 2:
        parts.append('Vigésima')
    if unit:
        parts.append(ORDINAL_UNITS[unit])
    return ' '.join(parts)


def class_label(number):
    """«12ª (Décima Segunda) Classe»."""
    if not number:
        return 'Iniciação'
    return f'{number}ª ({ordinal_feminine(number)}) Classe'


def date_long(day, upper=False):
    """«06 de Julho de 2026»."""
    if not day:
        return ''
    text = f'{day.day:02d} de {MONTHS[day.month - 1]} de {day.year}'
    return text.upper() if upper else text
