from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    edu_is_school = fields.Boolean(string='É uma escola')
    edu_school_type = fields.Selection(
        [
            ('general', 'Ensino geral'),
            ('technical', 'Técnico-profissional'),
            ('teacher_training', 'Formação de professores (magistério)'),
            ('mixed', 'Vários subsistemas'),
        ],
        string='Subsistema',
        default='general',
    )
    edu_ownership = fields.Selection(
        [
            ('public', 'Pública'),
            ('private', 'Privada'),
            ('public_private', 'Público-privada'),
            ('community', 'Comunitária'),
            ('religious', 'Religiosa'),
        ],
        string='Natureza',
    )
    edu_billing_mode = fields.Selection(
        [
            ('fee_free', 'Sem propina (só serviços pedidos)'),
            ('monthly', 'Propina mensal'),
            ('subsidized', 'Comparticipada (propina reduzida e subsídio do Estado)'),
        ],
        string='Modo de cobrança',
        default='monthly',
        help='Comanda a geração das propinas na matrícula.',
    )
    edu_level_ids = fields.Many2many('edu.level', string='Níveis de ensino')
    edu_institution_code = fields.Char(string='Código da instituição (MED)')
    edu_mined_code = fields.Char(string='N.º de registo no MED')
    edu_license_number = fields.Char(string='N.º do alvará / licença')
    edu_established_year = fields.Integer(string='Ano de fundação')
    edu_letterhead_subtitle = fields.Char(
        string='Subtítulo do cabeçalho',
        help='Linha impressa sob o nome nos documentos oficiais, por exemplo '
        '«II Ciclo do Ensino Técnico Profissional de Saúde».',
    )
    edu_motto = fields.Char(string='Lema')
    edu_director_name = fields.Char(string='Director(a) geral', help='Assina os documentos oficiais.')
    edu_pedagogical_director_name = fields.Char(
        string='Director(a) pedagógico(a)', help='Assina as pautas e os mapas de aproveitamento.'
    )
    edu_student_capacity = fields.Integer(string='Capacidade (alunos)')
    edu_current_year_id = fields.Many2one(
        'edu.academic.year', string='Ano lectivo em curso', compute='_compute_edu_current_year_id'
    )

    def _compute_edu_current_year_id(self):
        Year = self.env['edu.academic.year']
        for company in self:
            company.edu_current_year_id = Year.search(
                [('company_id', '=', company.id), ('is_current', '=', True)], limit=1
            )
