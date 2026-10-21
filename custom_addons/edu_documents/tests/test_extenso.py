from datetime import date

from odoo.addons.edu_documents.tools.extenso import (
    class_label,
    date_long,
    grade_text,
    number_words,
    ordinal_feminine,
)
from odoo.tests import BaseCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestExtenso(BaseCase):
    def test_numbers(self):
        expected = {0: 'zero', 1: 'um', 14: 'catorze', 16: 'dezasseis', 17: 'dezassete', 19: 'dezanove', 20: 'vinte',
                    21: 'vinte e um', 100: 'cem', 101: 'cento e um', 245: 'duzentos e quarenta e cinco',
                    1000: 'mil', 2026: 'dois mil e vinte e seis', 1500: 'mil e quinhentos'}  # fmt: skip
        for number, words in expected.items():
            self.assertEqual(number_words(number), words)

    def test_grades(self):
        self.assertEqual(grade_text(15), '15 (QUINZE) VALORES')
        self.assertEqual(grade_text(8, 'title'), '08 (Oito) Valores')
        self.assertEqual(grade_text(1), '01 (UM) VALOR')
        self.assertEqual(grade_text(9.5), '10 (DEZ) VALORES')

    def test_classes_and_dates(self):
        self.assertEqual(ordinal_feminine(12), 'Décima Segunda')
        self.assertEqual(ordinal_feminine(10), 'Décima')
        self.assertEqual(ordinal_feminine(7), 'Sétima')
        self.assertEqual(class_label(13), '13ª (Décima Terceira) Classe')
        self.assertEqual(date_long(date(2026, 7, 6)), '06 de Julho de 2026')
        self.assertEqual(date_long(date(2026, 9, 21), upper=True), '21 DE SETEMBRO DE 2026')
