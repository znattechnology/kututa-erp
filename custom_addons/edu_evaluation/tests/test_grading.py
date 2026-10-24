"""Casos dourados do motor (secPed-Express e Anexo III do RAA)."""

from odoo.addons.edu_evaluation.tools.grading import (
    CONDITIONAL,
    EXAM,
    GENERAL,
    GRADUATED,
    PENDING,
    PROMOTED,
    RETAINED,
    TECHNICAL,
    Rules,
    course_final,
    cumulative,
    decide,
    exam_class_mt3,
    frequency_classification,
    general_mt,
    has_global_exam,
    national_final,
    normalise,
    round_units,
    rounder,
    special_exam_result,
    technical_ca,
    technical_ct,
    technical_subject_approved,
    weighted_mean,
    with_adjustment,
)
from odoo.tests import BaseCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestGrading(BaseCase):
    def test_rounding(self):
        self.assertEqual([round_units(v) for v in (9.5, 9.49, 14, 12.5, 4.5)], [10, 9, 14, 13, 5])
        decimal2 = rounder('decimal2')
        self.assertEqual([decimal2(v) for v in (9.999, 12.3456, 14.8)], [10.0, 12.35, 14.8])

    def test_general(self):
        # MT = (MAC + NPT) / 2: teste 12 e prova 16 → 14 (grade.service.int-spec).
        self.assertEqual(general_mt(12, 16), 14)
        self.assertEqual(general_mt(14, 12), 13)
        self.assertIsNone(general_mt(14, None))
        self.assertEqual(weighted_mean([(12, 1), (16, 3)]), 15)
        self.assertEqual(normalise(8, 10, 20), 16)
        self.assertEqual(normalise(18, 20, 10), 18)
        # Classe de exame, III trimestre: (10 + 8 + 6) / 3 = 8 (primário, 6.ª classe).
        self.assertEqual(exam_class_mt3([10, 8], 6), 8)
        # MFED na 6.ª: 0,6 × 8 + 0,4 × 6 = 7,2 → 7; na 12.ª: 0,5/0,5.
        self.assertEqual(national_final(8, 6, 0.4), 7)
        self.assertEqual(national_final(13, 16, 0.5), 15)
        self.assertEqual(frequency_classification([10, 14, 18], GENERAL), 14)

    def test_technical_cumulative(self):
        # classificacao-frequencia.helper.spec
        self.assertEqual(cumulative([10, 14, 18]), [10, 12, 15])
        self.assertEqual(frequency_classification([10, 14, 18], TECHNICAL), 15)
        self.assertEqual(frequency_classification([8, 8, 14], TECHNICAL), 11)
        self.assertEqual(frequency_classification([14, 14, 8], TECHNICAL), 11)
        # Um trimestre sem classificação conta 0; os que ainda não tiveram notas ficam de fora.
        self.assertEqual(cumulative([12, None, 16]), [12, 6, 11])
        self.assertEqual(cumulative([None, None, 13]), [0, 0, 7])
        self.assertEqual(cumulative([12, None, None]), [12, 12, 12])
        self.assertEqual(frequency_classification([9, None, 14], TECHNICAL), 10)
        self.assertEqual(frequency_classification([12, None, 15], GENERAL), 9)
        self.assertEqual(frequency_classification([12, None, None], GENERAL), 12)
        self.assertIsNone(frequency_classification([None, None, None], TECHNICAL))
        self.assertIsNone(frequency_classification([], TECHNICAL))
        self.assertEqual(cumulative([11, 12, 12]), [11, 12, 12])
        self.assertEqual(frequency_classification([10, 10, 10], TECHNICAL, imported=17), 17)
        self.assertEqual(frequency_classification([15, 15, 15], TECHNICAL, imported=0), 0)
        self.assertEqual(technical_ct(8, 12), 10)
        self.assertEqual(technical_ct(14, 12), 13)
        self.assertEqual(technical_ct(None, 12), 12)

    def test_global_exam(self):
        # prova-global.helper.spec
        self.assertFalse(has_global_exam(2, 'scientific', 'Matemática'))
        self.assertFalse(has_global_exam(None, 'scientific', 'Matemática'))
        self.assertTrue(has_global_exam(3, 'scientific', 'Matemática'))
        # Técnica: só não têm PG as disciplinas só práticas do Anexo I (Despacho 60/08, art. 18.º, n.º 3).
        self.assertTrue(has_global_exam(5, 'technical', 'Redes'))
        self.assertTrue(has_global_exam(4, 'technical', 'Anatomia da Cabeça e Pescoço'))
        self.assertFalse(has_global_exam(4, 'technical', 'Projecto Tecnológico'))
        self.assertFalse(has_global_exam(4, 'technical', 'Práticas Oficinais'))
        self.assertFalse(has_global_exam(3, 'technical', 'Informática Aplicada'))
        self.assertFalse(has_global_exam(5, 'internship', 'Estágio'))
        # Fora da componente técnica, todas as disciplinas com 3 ou mais tempos têm PG (art. 18.º, n.º 1).
        for name in ('Educação Física', 'Informática'):
            self.assertTrue(has_global_exam(3, 'socio_cultural', name), name)
        self.assertTrue(has_global_exam(3, 'scientific', 'Física'))
        self.assertTrue(has_global_exam(3, 'scientific', 'Físico-Química'))
        self.assertTrue(has_global_exam(5, 'socio_cultural', 'Língua Portuguesa'))
        # computeCA
        self.assertIsNone(technical_ca(None, 15, True))
        self.assertEqual(technical_ca(14.3344, 15, True), 15)
        self.assertEqual(technical_ca(11.5521, 10.75, True), 11)
        self.assertEqual(technical_ca(12.49, None, True), 12)
        self.assertEqual(technical_ca(12.5, None, False), 13)
        self.assertEqual(technical_ca(14, 16, False), 14)
        self.assertEqual(technical_ca(14, 16, True), 15)
        self.assertEqual(technical_ca(14, 16, True, rounder('decimal2')), 14.8)

    def test_adjustment_and_course(self):
        self.assertIsNone(with_adjustment(None, 2))
        self.assertEqual([with_adjustment(9, 0), with_adjustment(9, 2), with_adjustment(19, 2)], [9, 11, 20])
        self.assertEqual(with_adjustment(9, 2, scale_max=10), 10)
        self.assertEqual(course_final(14, 17), 15)
        self.assertEqual(course_final(14, 17, internship=16, formula='internship'), 15)
        self.assertEqual(course_final(13), 13)
        self.assertEqual(special_exam_result(14, 11, improvement=True), 14)
        self.assertEqual(special_exam_result(12, 16, improvement=True), 16)
        self.assertEqual(special_exam_result(8, 12), 12)

    def test_decide(self):
        transition = Rules(conditional_max=2, floor=7, forbidden_pairs=[('LP', 'MAT')])
        self.assertEqual(decide({'LP': 14, 'MAT': 12}, transition).status, PROMOTED)
        self.assertEqual(decide({'LP': 14}, Rules(terminal=True)).status, GRADUATED)
        self.assertEqual(decide({'LP': 3}, Rules(auto_promote=True)).status, PROMOTED)
        self.assertEqual(decide({'LP': 14}, transition, excluded_absence=True).status, RETAINED)
        self.assertEqual(decide({'LP': 14}, transition, complete=False).status, PENDING)
        # Até duas negativas entre 7 e 9 → transita condicionalmente (promotion-transicao.int-spec).
        self.assertEqual(decide({'LP': 8, 'FIS': 12}, transition).status, CONDITIONAL)
        self.assertEqual(decide({'LP': 7, 'FIS': 9}, transition).status, CONDITIONAL)
        self.assertEqual(decide({'LP': 6}, transition).status, RETAINED)
        self.assertEqual(decide({'LP': 9, 'QUI': 9, 'FIS': 9}, transition).status, RETAINED)
        # Não simultaneamente Português e Matemática (art. 25.º, n.º 2).
        self.assertEqual(decide({'LP': 9, 'MAT': 9}, transition).status, RETAINED)
        # Classe terminal: recurso até 4 negativas, sem Português e Matemática juntas (art. 31.º).
        terminal = Rules(terminal=True, exam_max=4, forbidden_pairs=[('LP', 'MAT')])
        decision = decide({'LP': 9, 'FIS': 5, 'QUI': 8, 'MAT': 12}, terminal)
        self.assertEqual((decision.status, decision.negatives), (EXAM, ['FIS', 'LP', 'QUI']))
        self.assertEqual(decide({'LP': 9, 'MAT': 8}, terminal).status, RETAINED)
        # Primário: todas ≥ 5 (promotion-primario.int-spec).
        primary = Rules(pass_grade=5, floor=None)
        self.assertEqual(decide({'LP': 4}, primary).status, RETAINED)
        self.assertEqual(decide({'LP': 6}, primary).status, PROMOTED)
        self.assertEqual(decide({'LP': 6}, primary, low_attendance=True).status, RETAINED)
        # Recurso (Dec. 424/25, art. 31.º): 9.ª e 12.ª até três negativas entre 6 e 9; 6.ª duas entre 3 e 4.
        ninth = Rules(terminal=True, exam_max=3, exam_floor=6, forbidden_pairs=[('LP', 'MAT')])
        self.assertEqual(decide({'LP': 9, 'FIS': 8, 'QUI': 6}, ninth).status, EXAM)
        self.assertEqual(decide({'LP': 9, 'FIS': 8, 'QUI': 5}, ninth).status, RETAINED)
        self.assertEqual(decide({'LP': 9, 'FIS': 8, 'QUI': 7, 'BIO': 9}, ninth).status, RETAINED)
        sixth = Rules(pass_grade=5, floor=None, terminal=True, exam_max=2, exam_floor=3)
        self.assertEqual(decide({'LP': 4, 'CN': 3}, sixth).status, EXAM)
        self.assertEqual(decide({'LP': 4, 'CN': 2}, sixth).status, RETAINED)
        self.assertEqual(decide({'LP': 4, 'CN': 3, 'EMP': 4}, sixth).status, RETAINED)
        # Técnico (Despacho 60/08, art. 29.º): até duas negativas, sem nota mínima; 3 a 5 vão a recurso.
        technical = Rules(conditional_max=2, floor=None, exam_max=5)
        self.assertEqual(decide({'LP': 3, 'FIS': 9}, technical).status, CONDITIONAL)
        self.assertEqual(decide({'LP': 3, 'FIS': 9, 'QUI': 9}, technical).status, EXAM)

    def test_technical_multi_year_subject(self):
        # Art. 28.º, n.º 2: CFD ≥ 10, pelo menos 7 no ano terminal e sem negativa em dois anos seguidos.
        self.assertTrue(technical_subject_approved(12, 11, 13))
        self.assertTrue(technical_subject_approved(10, 12, 8))
        self.assertFalse(technical_subject_approved(11, 6, 16))
        self.assertFalse(technical_subject_approved(10, 9, 9))
        self.assertFalse(technical_subject_approved(9, 12, None))
