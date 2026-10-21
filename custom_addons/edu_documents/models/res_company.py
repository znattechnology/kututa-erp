from odoo import fields, models

GENDERS = [('m', 'Masculino'), ('f', 'Feminino')]


class ResCompany(models.Model):
    _inherit = 'res.company'

    edu_director_gender = fields.Selection(GENDERS, string='Género do(a) director(a)', default='m')
    edu_pedagogical_director_gender = fields.Selection(
        GENDERS, string='Género do(a) director(a) pedagógico(a)', default='f'
    )
    edu_director_title = fields.Char(
        string='Cargo do(a) director(a)', default='Director Geral', help='Como aparece nas assinaturas.'
    )
    edu_secretary_name = fields.Char(string='Chefe da secretaria pedagógica')
    edu_official_line = fields.Char(
        string='Linha oficial do cabeçalho',
        help='Terceira linha do cabeçalho de Estado (REPÚBLICA DE ANGOLA / MINISTÉRIO DA EDUCAÇÃO / …), por exemplo '
        '«ENSINO SECUNDÁRIO TÉCNICO-PROFISSIONAL».',
    )
    edu_document_city = fields.Char(string='Localidade dos documentos', help='Por exemplo, Sumbe.')
    edu_supervisor_school = fields.Char(
        string='Escola pública de tutela',
        help='Escolas privadas: a escola pública que visa e autentica os documentos para transferência.',
    )
    edu_supervisor_director = fields.Char(string='Director(a) da escola de tutela')
    edu_licence_text = fields.Char(string='Licença', help='Por exemplo, «Sob Licença nº 12/020».')
