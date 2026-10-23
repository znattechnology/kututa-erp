from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'edu')
class TestEduGuardianPage(TransactionCase):
    """Encarregados como no secPed: criar segue para vincular; o mesmo NIF ou BI não se regista duas vezes; o aluno tem
    um só encarregado principal (o novo principal tira o lugar ao anterior)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clerk = cls.env['res.users'].create(
            {
                'name': 'Secretaria',
                'login': 'secretaria_enc',
                'group_ids': [Command.set([cls.env.ref('edu_core.group_edu_user').id])],
            }
        )
        cls.student = cls.env['edu.student'].create({'name': 'Ana Kiala'})
        cls.Page = cls.env['edu.guardian.page'].with_user(cls.clerk)

    def test_create_and_link(self):
        Page = self.Page
        with self.assertRaises(UserError):
            Page.create_guardian({'name': 'Sem telefone'})
        mother = Page.create_guardian({'name': 'Maria Kiala', 'phone': '923000000', 'id_number': '004567890LA042'})
        with self.assertRaises(UserError):
            Page.create_guardian({'name': 'Outra Maria', 'phone': '924000000', 'id_number': '004567890LA042'})
        father = Page.create_guardian({'name': 'João Kiala', 'phone': '925000000'})

        # O primeiro encarregado é o principal, mesmo sem a caixa marcada.
        Page.link(self.student.id, mother['id'], 'mother', {'is_primary': False, 'can_pickup': True})
        links = Page.student_guardians(self.student.id)
        self.assertEqual(
            [(lk['guardian'], lk['relationship'], lk['primary']) for lk in links], [('Maria Kiala', 'Mãe', True)]
        )
        with self.assertRaises(UserError):
            Page.link(self.student.id, mother['id'], 'mother', {})

        # O novo principal tira o lugar ao anterior.
        Page.link(self.student.id, father['id'], 'father', {'is_primary': True})
        primary = {lk['guardian']: lk['primary'] for lk in Page.student_guardians(self.student.id)}
        self.assertEqual(primary, {'Maria Kiala': False, 'João Kiala': True})

        # Desvincular o principal passa o lugar ao outro encarregado.
        father_link = next(lk for lk in Page.student_guardians(self.student.id) if lk['guardian'] == 'João Kiala')
        result = Page.unlink_link(father_link['id'])
        self.assertEqual([(lk['guardian'], lk['primary']) for lk in result['links']], [('Maria Kiala', True)])
        self.assertEqual(result['promoted'], 'Maria Kiala')
        with self.assertRaises(UserError):
            Page.link(self.student.id, father['id'], 'cousin', {})

        rows = {r['name']: r for r in Page.listing()['rows']}
        self.assertEqual([lk['student'] for lk in rows['Maria Kiala']['links']], ['Ana Kiala'])
        self.assertFalse(rows['João Kiala']['links'])
        self.assertEqual([g['name'] for g in Page.search_guardians('925')], ['João Kiala'])

        # O mesmo BI com espaços e minúsculas, ou de um encarregado arquivado, também é repetido.
        self.env['edu.guardian'].browse(mother['id']).active = False
        with self.assertRaises(UserError):
            Page.create_guardian({'name': 'Outra', 'phone': '926000000', 'id_number': ' 004567890la042 '})
