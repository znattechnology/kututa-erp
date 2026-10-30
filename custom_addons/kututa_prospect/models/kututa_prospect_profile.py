from odoo import Command, api, fields, models
from odoo.fields import Domain

PROVINCIAS = [
    ('bengo', 'Bengo'),
    ('benguela', 'Benguela'),
    ('bie', 'Bié'),
    ('cabinda', 'Cabinda'),
    ('cuando', 'Cuando'),
    ('cubango', 'Cubango'),
    ('cuanza_norte', 'Cuanza Norte'),
    ('cuanza_sul', 'Cuanza Sul'),
    ('cunene', 'Cunene'),
    ('huambo', 'Huambo'),
    ('huila', 'Huíla'),
    ('icolo_bengo', 'Ícolo e Bengo'),
    ('luanda', 'Luanda'),
    ('lunda_norte', 'Lunda Norte'),
    ('lunda_sul', 'Lunda Sul'),
    ('malanje', 'Malanje'),
    ('moxico', 'Moxico'),
    ('moxico_leste', 'Moxico Leste'),
    ('namibe', 'Namibe'),
    ('uige', 'Uíge'),
    ('zaire', 'Zaire'),
]
FONTES = [
    ('google_places', 'Google Places API'),
    ('lista_med', 'Lista oficial do MED'),
    ('lista_mescti', 'Lista oficial do MESCTI'),
    ('lista_publica', 'Outra lista pública'),
    ('site_organizacao', 'Site da própria organização'),
    ('manual', 'Recolha manual (verificada por uma pessoa)'),
]  # Sem redes sociais nem página de resultados do Google: proibido pelos termos dessas plataformas.
CANAIS = [('email', 'E-mail'), ('telefone', 'Telefone'), ('whatsapp', 'WhatsApp (fora do Odoo)'), ('visita', 'Visita')]


class KututaProspectProfile(models.Model):
    _name = 'kututa.prospect.profile'
    _description = 'Perfil de prospecção (um por produto)'
    _order = 'sequence, id'

    name = fields.Char('Nome', required=True)
    code = fields.Char(
        'Código', required=True, help='Identificador usado pelo n8n e pela IA (escolas, universidade, …).'
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True
    )
    product_tmpl_ids = fields.Many2many(
        'product.template',
        string='Produtos',
        domain="[('company_id', 'in', [company_id, False]), ('default_code', '=like', 'KUT-%')]",
    )
    segmento = fields.Text('Segmento-alvo', help='Descrição em linguagem natural; vai para a IA.')
    query_ids = fields.One2many('kututa.prospect.query', 'profile_id', 'Fontes e consultas')
    cargos = fields.Text('Cargos a contactar', help='Um por linha.')
    criterio_ids = fields.One2many('kututa.prospect.criterion', 'profile_id', 'Critérios de qualificação')
    dores = fields.Text(help='Uma por linha.')
    proposta_valor = fields.Html('Proposta de valor', sanitize=True)
    tom = fields.Selection(
        [('institucional', 'Institucional'), ('proximo', 'Próximo'), ('tecnico', 'Técnico')],
        default='institucional',
        required=True,
    )
    tom_notas = fields.Text('Notas sobre o tom')
    canal_email = fields.Boolean('E-mail', default=True)
    canal_telefone = fields.Boolean('Telefone', default=True)
    canal_whatsapp = fields.Boolean('WhatsApp (fora do Odoo)')
    canal_visita = fields.Boolean('Visita')
    cadencia_ids = fields.One2many('kututa.prospect.cadence', 'profile_id', 'Cadência')
    team_id = fields.Many2one('crm.team', 'Equipa de vendas', required=True)
    stage_review_id = fields.Many2one(
        'crm.stage',
        'Etapa de revisão',
        default=lambda self: self.env.ref('kututa_prospect.stage_para_rever', raise_if_not_found=False),
    )
    prefixos_produtos = fields.Char(
        'Referências dos produtos', help='Prefixos das referências separados por vírgulas, por exemplo «KUT-ESC-».'
    )
    limites = fields.Text(
        'O que não prometer', help='Limites do produto que a mensagem não pode esconder (vai para a IA).'
    )

    _code_unique = models.Constraint('UNIQUE(code, company_id)', 'Já há um perfil com este código.')

    def action_ligar_produtos(self):
        """Liga os produtos da tabela de preços (KUT-*) da empresa do perfil pelas referências."""
        for perfil in self:
            prefixos = [p.strip() for p in (perfil.prefixos_produtos or '').split(',') if p.strip()]
            if not prefixos:
                continue
            dominio = Domain.OR([[('default_code', '=like', f'{p}%')] for p in prefixos])
            produtos = self.env['product.template'].search(
                dominio & Domain('company_id', 'in', [perfil.company_id.id, False])
            )
            perfil.product_tmpl_ids = [Command.set(produtos.ids)]
        return True

    @api.model
    def _ligar_todos_os_produtos(self):
        self.search([('prefixos_produtos', '!=', False)]).action_ligar_produtos()

    @api.model
    def _activos(self):
        return self.sudo().search([('active', '=', True)])


class KututaProspectQuery(models.Model):
    _name = 'kututa.prospect.query'
    _description = 'Fonte e consulta de um perfil de prospecção'
    _order = 'profile_id, id'

    profile_id = fields.Many2one('kututa.prospect.profile', 'Perfil', required=True, ondelete='cascade', index=True)
    profile_code = fields.Char(related='profile_id.code', string='Código do perfil')
    company_id = fields.Many2one(related='profile_id.company_id', store=True, index=True)
    fonte = fields.Selection(FONTES, required=True, default='google_places')
    consulta = fields.Char('Pesquisa', help='Texto a pesquisar, por exemplo «colégio».')
    provincia = fields.Selection(PROVINCIAS, 'Província')
    cidade = fields.Char()
    url_lista = fields.Char('Endereço da lista')
    active = fields.Boolean(default=True)
    ultima_execucao = fields.Datetime('Última entrega', readonly=True)


class KututaProspectCriterion(models.Model):
    _name = 'kututa.prospect.criterion'
    _description = 'Critério de qualificação de um perfil de prospecção'
    _order = 'profile_id, sequence, id'

    profile_id = fields.Many2one('kututa.prospect.profile', 'Perfil', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='profile_id.company_id', store=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Critério', required=True)
    peso = fields.Integer(default=3)
    obrigatorio = fields.Boolean('Obrigatório', help='Se falhar, a pontuação do perfil fica limitada a 30.')

    _peso_valido = models.Constraint('CHECK(peso BETWEEN 1 AND 5)', 'O peso vai de 1 a 5.')


class KututaProspectCadence(models.Model):
    _name = 'kututa.prospect.cadence'
    _description = 'Passo de seguimento de um perfil de prospecção'
    _order = 'profile_id, sequence, dias_apos, id'

    profile_id = fields.Many2one('kututa.prospect.profile', 'Perfil', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='profile_id.company_id', store=True, index=True)
    sequence = fields.Integer(default=10)
    dias_apos = fields.Integer('Dias após a verificação', default=0)
    canal = fields.Selection(CANAIS, required=True, default='email')
    activity_type_id = fields.Many2one('mail.activity.type', 'Tipo de actividade')
    nota = fields.Char()
