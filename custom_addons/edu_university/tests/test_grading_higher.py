from odoo.tests import BaseCase, tagged

from ..tools.grading_higher import ADMITTED, EXCLUDED, EXEMPT, PENDING, Rules, frequency_mark, resolve


@tagged('post_install', '-at_install', 'edu')
class TestGradingHigher(BaseCase):
    """Casos calculados à mão sobre o regulamento por defeito (aprovação 10, dispensa 14, admissão 7, assiduidade
    75 %, 40 % MF + 60 % exame, mínimo 10 no exame, especial a 10, arredondamento às unidades)."""

    rules = Rules()

    def test_frequency_mark(self):
        self.assertIsNone(frequency_mark([]))
        # 1.ª frequência 12 (peso 1), 2.ª 15 (peso 1), trabalho 18 (peso 0,5): (12 + 15 + 9) / 2,5 = 14,4
        self.assertAlmostEqual(frequency_mark([(12, 1), (15, 1), (18, 0.5)]), 14.4)

    def test_exempt(self):
        outcome = resolve(self.rules, 14.4)
        self.assertEqual(
            (outcome.status, outcome.final, outcome.passed, outcome.source), (EXEMPT, 14, True, 'frequency')
        )
        self.assertEqual(resolve(self.rules, 13.99).status, ADMITTED)

    def test_excluded(self):
        outcome = resolve(self.rules, 6.5)
        self.assertEqual((outcome.status, outcome.final, outcome.passed), (EXCLUDED, 7, False))
        # MF de dispensa, mas com 70 % de presenças: excluído.
        self.assertEqual(resolve(self.rules, 16, attendance=70).status, EXCLUDED)
        self.assertEqual(resolve(self.rules, 16, attendance=75).status, EXEMPT)
        # O excluído não vai ao normal; ao recurso só se o regulamento deixar.
        self.assertFalse(resolve(self.rules, 6, normal=15).passed)
        self.assertFalse(resolve(self.rules, 6, appeal=15).passed)
        lenient = Rules(appeal_for_excluded=True)
        # 0,4 × 6 + 0,6 × 15 = 11,4 → 11
        self.assertEqual(resolve(lenient, 6, appeal=15).final, 11)

    def test_normal_exam(self):
        self.assertEqual(resolve(self.rules, 10).status, ADMITTED)
        self.assertEqual(resolve(self.rules, 10).source, '')
        # 0,4 × 10 + 0,6 × 12 = 11,2 → 11
        outcome = resolve(self.rules, 10, normal=12)
        self.assertEqual((outcome.final, outcome.passed, outcome.source), (11, True, 'normal'))
        # 0,4 × 8 + 0,6 × 11 = 9,8 → 10 (arredonda para cima): aprova.
        self.assertEqual(resolve(self.rules, 8, normal=11).final, 10)
        # 0,4 × 8 + 0,6 × 10,5 = 9,5 → 10
        self.assertTrue(resolve(self.rules, 8, normal=10.5).passed)
        # 0,4 × 7 + 0,6 × 10 = 8,8 → 9: reprova.
        self.assertEqual(
            (resolve(self.rules, 7, normal=10).final, resolve(self.rules, 7, normal=10).passed), (9, False)
        )
        # MF 13, exame 9 (abaixo do mínimo): reprova com 9, apesar de 0,4 × 13 + 0,6 × 9 = 10,6.
        outcome = resolve(self.rules, 13, normal=9)
        self.assertEqual((outcome.final, outcome.passed), (9, False))

    def test_only_exam(self):
        rules = Rules(frequency_weight=0, exam_min=0)
        self.assertEqual(resolve(rules, 12, normal=9.5).final, 10)
        self.assertEqual(resolve(rules, 12, normal=9.4).passed, False)

    def test_appeal(self):
        # Reprovou no normal com 6; no recurso 13: 0,4 × 9 + 0,6 × 13 = 11,4 → 11.
        outcome = resolve(self.rules, 9, normal=6, appeal=13)
        self.assertEqual((outcome.final, outcome.passed, outcome.source), (11, True, 'appeal'))
        # Faltou ao normal e fez recurso.
        self.assertEqual(resolve(self.rules, 9, appeal=10).final, 10)

    def test_special(self):
        outcome = resolve(self.rules, 5, normal=4, appeal=6, special=16)
        self.assertEqual((outcome.final, outcome.passed, outcome.source), (10, True, 'special'))
        self.assertEqual(resolve(Rules(special_fixed=False), 5, special=16).final, 16)
        self.assertFalse(resolve(self.rules, 5, special=8).passed)

    def test_improvement(self):
        self.assertEqual(resolve(self.rules, 14, improvement=17).final, 17)
        self.assertEqual(resolve(self.rules, 15, improvement=12).final, 15)
        self.assertEqual(resolve(self.rules, 15, improvement=12).source, 'frequency')

    def test_pending_and_tenth(self):
        self.assertEqual(resolve(self.rules, None).status, PENDING)
        self.assertIsNone(resolve(self.rules, None).final)
        self.assertEqual(resolve(Rules(rounding='tenth'), 14.45).final, 14.5)
