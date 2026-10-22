from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduPeople(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.student = cls.env['edu.student'].create(
            {
                'name': 'Ana Kiala',
                'birth_date': date(2010, 5, 3),
                'gender': 'female',
                'id_number': '006543210LA045',
                'father_name': 'João Kiala',
                'mother_name': 'Maria Kiala',
                'birth_state_id': cls.env.ref('l10n_ao.state_ao_lua').id,
            }
        )
        cls.mother = cls.env['edu.guardian'].create(
            {'name': 'Maria Kiala', 'phone': '+244 923 000 000', 'vat': '004567891LA041', 'occupation': 'Enfermeira'}
        )
        cls.father = cls.env['edu.guardian'].create({'name': 'João Kiala', 'phone': '+244 924 000 000'})

    def test_student_partner(self):
        partner = self.student.partner_id
        self.assertEqual(partner.name, 'Ana Kiala')
        self.assertFalse(partner.is_company)
        self.assertEqual(partner.company_id, self.env.company)
        self.assertGreaterEqual(self.student.age, 15)
        self.assertEqual(self.student.nationality_id, self.env.ref('base.ao'))
        with self.assertRaises(ValidationError):
            self.env['edu.student'].create({'name': 'Futuro', 'birth_date': date(2099, 1, 1)})

    def test_matricula_number(self):
        self.student._assign_matricula_number(year=2026, date=date(2026, 9, 1))
        self.assertEqual(self.student.matricula_number, '2026-0001')
        self.assertEqual(self.student.matricula_seq, 1)
        self.assertEqual(self.student.enrollment_date, date(2026, 9, 1))
        self.assertEqual(self.student.display_name, '2026-0001 · Ana Kiala')
        # Vitalício: a 2.ª matrícula não muda o número.
        self.student._assign_matricula_number(year=2027)
        self.assertEqual(self.student.matricula_number, '2026-0001')
        with self.assertRaises(UserError):
            self.student.matricula_number = '2026-0099'
        # A sequência é global na escola e não reinicia com o ano.
        other = self.env['edu.student'].create({'name': 'Bento Mateus'})
        other._assign_matricula_number(year=2027)
        self.assertEqual(other.matricula_number, '2027-0002')
        self.assertEqual(self.env['edu.student'].name_search('2027-0002')[0][0], other.id)
        with self.assertRaises(UserError):
            other.unlink()

    def test_matricula_import(self):
        imported = (
            self.env['edu.student']
            .with_context(edu_matricula_import=True)
            .create({'name': 'Migrado', 'matricula_number': '2024-0150', 'matricula_year': 2024, 'matricula_seq': 150})
        )
        self.env['edu.student']._sync_matricula_sequence(self.env.company)
        self.student._assign_matricula_number(year=2026)
        self.assertEqual(self.student.matricula_number, '2026-0151')
        self.assertTrue(imported.matricula_number)

    def test_guardians(self):
        first = self.env['edu.student.guardian'].create(
            {'student_id': self.student.id, 'guardian_id': self.mother.id, 'relationship': 'mother'}
        )
        self.assertTrue(first.is_primary)
        second = self.env['edu.student.guardian'].create(
            {'student_id': self.student.id, 'guardian_id': self.father.id, 'relationship': 'father'}
        )
        self.assertFalse(second.is_primary)
        self.assertEqual(self.student.primary_guardian_id, self.mother)
        second.action_make_primary()
        self.assertEqual(self.student.primary_guardian_id, self.father)
        self.assertFalse(first.is_primary)
        self.assertEqual(self.mother.student_count, 1)
        self.assertEqual(self.mother.partner_id.vat, '004567891LA041')
        with self.assertRaises(UserError):
            self.mother.unlink()

    def test_teacher(self):
        subject = self.env['edu.subject'].create({'name': 'Matemática', 'code': 'MAT'})
        teacher = self.env['hr.employee'].create(
            {'name': 'Pedro Docente', 'edu_is_teacher': True, 'edu_subject_ids': [(6, 0, subject.ids)]}
        )
        self.assertIn(teacher, self.env['hr.employee'].search([('edu_is_teacher', '=', True)]))

    def test_secretary_manages_students(self):
        """A secretaria (só group_edu_user) cria e edita alunos e encarregados, que herdam de res.partner."""
        clerk = self.env['res.users'].create(
            {
                'name': 'Secretária',
                'login': 'secretaria_people',
                'group_ids': [Command.set([self.env.ref('edu_core.group_edu_user').id])],
            }
        )
        student = self.env['edu.student'].with_user(clerk).create({'name': 'Aluno da Secretaria'})
        student.phone = '+244 923 111 222'
        guardian = self.env['edu.guardian'].with_user(clerk).create({'name': 'Encarregado da Secretaria'})
        guardian.vat = '004567891LA041'
        self.assertEqual(student.partner_id.phone, '+244 923 111 222')
