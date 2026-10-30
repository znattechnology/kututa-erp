import re
from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import email_normalize, html2plaintext

from ..tools import normalizar
from ..tools.trust import is_trusted, trusted

# Só mudam pelos métodos do módulo (verificar, rejeitar, classificar); nunca por escrita directa nem pelo contexto.
CAMPOS_PROTEGIDOS = {
    'kp_verificacao',
    'kp_verificado_por',
    'kp_verificado_em',
    'kp_motivo_rejeicao',
    'kp_score_ids',
    'kp_justificacao',
    'kp_classificado_em',
    'kp_modelo_ia',
    'kp_reter_ate',
}
VERIFICACAO = [('nao_verificado', 'Por verificar'), ('verificado', 'Verificado'), ('rejeitado', 'Rejeitado')]


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    kp_profile_id = fields.Many2one('kututa.prospect.profile', 'Perfil de prospecção', index=True, tracking=True)
    kp_produto_principal_id = fields.Many2one('kututa.prospect.profile', 'Produto principal', tracking=True)
    kp_produto_secundario_ids = fields.Many2many(
        'kututa.prospect.profile', 'crm_lead_kp_produto_secundario_rel', 'lead_id', 'profile_id', 'Outros produtos'
    )
    kp_score_ids = fields.One2many('kututa.prospect.score', 'lead_id', 'Pontuações')
    kp_pontuacao = fields.Integer('Pontuação', compute='_compute_kp_pontuacao', store=True, index=True)
    kp_justificacao = fields.Text('Justificação da IA')
    kp_classificado_em = fields.Datetime('Classificado em', readonly=True)
    kp_modelo_ia = fields.Char('Modelo de IA', readonly=True)
    kp_fonte_ids = fields.One2many('kututa.prospect.source', 'lead_id', 'Fontes dos dados')
    kp_fonte_count = fields.Integer('N.º de fontes', compute='_compute_kp_fonte_count')
    kp_place_id = fields.Char('Google place_id', index=True)
    kp_nif = fields.Char('NIF', index=True)
    kp_telefone = fields.Char('Telefone normalizado', compute='_compute_kp_telefone', store=True, index=True)
    kp_verificacao = fields.Selection(VERIFICACAO, 'Verificação', tracking=True, index=True)
    kp_verificado_por = fields.Many2one('res.users', 'Verificado por', readonly=True)
    kp_verificado_em = fields.Datetime('Verificado em', readonly=True)
    kp_motivo_rejeicao = fields.Char('Motivo da rejeição', readonly=True)
    kp_dedup_key = fields.Char('Chave de deduplicação', compute='_compute_kp_dedup_key', store=True, index=True)
    kp_rascunho = fields.Html('Rascunho da mensagem', sanitize=True)
    kp_excluido = fields.Boolean('Excluído', compute='_compute_kp_excluido', search='_search_kp_excluido')
    kp_reter_ate = fields.Date('Apagar dados de contacto em', readonly=True)

    @api.depends('kp_score_ids.pontuacao', 'kp_score_ids.profile_id', 'kp_produto_principal_id')
    def _compute_kp_pontuacao(self):
        for lead in self:
            principal = lead.kp_produto_principal_id
            lead.kp_pontuacao = next((s.pontuacao for s in lead.kp_score_ids if s.profile_id == principal), 0)

    @api.depends('kp_fonte_ids')
    def _compute_kp_fonte_count(self):
        for lead in self:
            lead.kp_fonte_count = len(lead.kp_fonte_ids)

    @api.depends('phone')
    def _compute_kp_telefone(self):
        for lead in self:
            lead.kp_telefone = normalizar.telefone(lead.phone)

    @api.depends('kp_nif', 'kp_telefone', 'partner_name', 'city')
    def _compute_kp_dedup_key(self):
        for lead in self:
            lead.kp_dedup_key = normalizar.chave_dedup(lead.kp_nif, lead.kp_telefone, lead.partner_name, lead.city)

    def _kp_chaves(self):
        self.ensure_one()
        return {
            'nif': self.kp_nif,
            'email': self.email_normalized or email_normalize(self.email_from or ''),
            'telefone': self.kp_telefone,
            'chave_nome_cidade': normalizar.chave_nome_cidade(self.partner_name, self.city),
        }

    @api.depends('kp_nif', 'email_normalized', 'kp_telefone', 'partner_name', 'city')
    def _compute_kp_excluido(self):
        Exclusao = self.env['kututa.prospect.exclusion']
        for lead in self:
            lead.kp_excluido = Exclusao._excluido(company=lead.company_id or self.env.company, **lead._kp_chaves())

    def _search_kp_excluido(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        exclusoes = self.env['kututa.prospect.exclusion'].sudo().search([('company_id', 'in', self.env.companies.ids)])
        emails = set(exclusoes.mapped('email_normalized')) | set(
            self.env['mail.blacklist'].sudo().search([('email', '!=', False)]).mapped('email')
        )
        telefones = set(exclusoes.mapped('phone_sanitized')) | set(
            self.env['phone.blacklist'].sudo().search([('number', '!=', False)]).mapped('number')
        )
        dominio = [
            '|',
            '|',
            ('kp_nif', 'in', [n for n in exclusoes.mapped('nif') if n]),
            ('email_normalized', 'in', [e for e in emails if e]),
            ('kp_telefone', 'in', [t for t in telefones if t]),
        ]
        ids = self.with_context(active_test=False).search(dominio).ids
        chaves = {c for c in exclusoes.mapped('chave_nome_cidade') if c}
        if chaves:
            candidatos = self.with_context(active_test=False).search([('kp_profile_id', '!=', False)])
            ids += [
                lead.id for lead in candidatos if normalizar.chave_nome_cidade(lead.partner_name, lead.city) in chaves
            ]
        positivo = (operator == '=') == value
        return [('id', 'in' if positivo else 'not in', ids)]

    # ------------------------------------------------------------------ guardas
    @api.model_create_multi
    def create(self, vals_list):
        confiavel = is_trusted(self.env)
        for vals in vals_list:
            if not vals.get('kp_profile_id'):
                continue
            if not confiavel:
                # Um lead de prospecção nasce sempre por verificar, na etapa de revisão do perfil.
                for campo in CAMPOS_PROTEGIDOS:
                    vals.pop(campo, None)
                vals['kp_verificacao'] = 'nao_verificado'
            vals.setdefault('kp_verificacao', 'nao_verificado')
            if 'kp_nif' in vals:
                vals['kp_nif'] = normalizar.nif(vals['kp_nif'])
            perfil = self.env['kututa.prospect.profile'].sudo().browse(vals['kp_profile_id'])
            vals.setdefault('team_id', perfil.team_id.id)
            if perfil.stage_review_id and vals['kp_verificacao'] == 'nao_verificado':
                vals['stage_id'] = perfil.stage_review_id.id
                vals.setdefault('type', 'opportunity')
        leads = super().create(vals_list)
        for lead in leads.filtered('kp_profile_id'):
            # Vale para qualquer origem: formulário, importação, API ou n8n (este já filtra antes).
            if lead.kp_excluido:
                raise UserError(
                    self.env._(
                        '«%s» está na lista de exclusão da prospecção: não se cria um lead de prospecção para '
                        'esta organização.',
                        lead.partner_name or lead.name,
                    )
                )
        return leads

    def write(self, vals):
        if vals.get('kp_rascunho'):
            self._kp_validar_afirmacao_agt(vals['kp_rascunho'])
        if not is_trusted(self.env):
            proibidos = CAMPOS_PROTEGIDOS & set(vals)
            if proibidos and self.filtered('kp_profile_id') or {'kp_verificacao'} & set(vals):
                raise AccessError(
                    self.env._('A verificação e a classificação da prospecção só mudam pelos botões próprios.')
                )
            if 'kp_nif' in vals:
                vals['kp_nif'] = normalizar.nif(vals['kp_nif'])
            if 'stage_id' in vals:
                presos = self.filtered(
                    lambda lead: (
                        lead.kp_profile_id
                        and lead.kp_verificacao != 'verificado'
                        and lead.stage_id == lead.kp_profile_id.stage_review_id
                        and vals['stage_id'] != lead.stage_id.id
                    )
                )
                if presos:
                    raise UserError(self.env._('Um lead de prospecção só sai de «Para rever» depois de verificado.'))
            if 'kp_profile_id' in vals and self.filtered(lambda lead: lead.kp_verificacao == 'verificado'):
                raise UserError(self.env._('O perfil de um lead verificado já não muda.'))
        return super().write(vals)

    # ------------------------------------------------------------------ verificação
    def _kp_verificar_permissao(self):
        if not self.env.user.has_group('kututa_prospect.group_prospect_user'):
            raise AccessError(self.env._('Só a equipa de prospecção verifica leads.'))
        gestor = self.env.user.has_group('kututa_prospect.group_prospect_manager')
        for lead in self:
            if not lead.kp_profile_id:
                raise UserError(self.env._('«%s» não é um lead de prospecção.', lead.name))
            if not gestor and lead.team_id not in self.env.user.crm_team_ids:
                raise AccessError(self.env._('Só a equipa de «%s» o pode verificar.', lead.name))

    def _kp_etapa_seguinte(self):
        self.ensure_one()
        revisao = self.kp_profile_id.stage_review_id
        dominio = [
            ('is_won', '=', False),
            ('id', '!=', revisao.id),
            ('sequence', '>=', revisao.sequence),
            '|',
            ('team_ids', '=', False),
            ('team_ids', 'in', self.team_id.ids),
        ]
        return self.env['crm.stage'].search(dominio, order='sequence, id', limit=1)

    def action_kp_verificar(self):
        self._kp_verificar_permissao()
        for lead in self:
            if lead.kp_verificacao == 'verificado':
                continue
            if lead.kp_excluido:
                raise UserError(self.env._('«%s» está na lista de exclusão: não se verifica.', lead.name))
            vals = {
                'kp_verificacao': 'verificado',
                'kp_verificado_por': self.env.uid,
                'kp_verificado_em': fields.Datetime.now(),
                'kp_motivo_rejeicao': False,
                'kp_reter_ate': False,
            }
            seguinte = lead._kp_etapa_seguinte()
            if seguinte:
                vals['stage_id'] = seguinte.id
            if not lead.user_id:
                vals['user_id'] = self.env.uid
            with trusted(self.env):
                lead.write(vals)
                # O vendedor confirmou os dados na fonte própria da organização: deixam de depender do Google.
                lead.sudo().write(
                    {
                        'kp_fonte_ids': [
                            fields.Command.create(
                                {'campo': 'verificação', 'fonte': 'manual', 'url': lead.website or False}
                            )
                        ]
                    }
                )
            lead._kp_criar_cadencia()
        return True

    def _kp_criar_cadencia(self):
        self.ensure_one()
        hoje = fields.Date.context_today(self)
        tipo_omissao = self.env.ref('mail.mail_activity_data_todo')
        for passo in self.kp_profile_id.cadencia_ids:
            canal = dict(passo._fields['canal'].selection).get(passo.canal)
            self.activity_schedule(
                activity_type_id=(passo.activity_type_id or tipo_omissao).id,
                date_deadline=hoje + timedelta(days=passo.dias_apos),
                summary=f'{canal}: {passo.nota}' if passo.nota else canal,
                user_id=(self.user_id or self.env.user).id,
            )

    def _kp_rejeitar(self, motivo, excluir=False):
        self._kp_verificar_permissao()
        meses = self.env['ir.config_parameter'].sudo().get_int('kututa_prospect.meses_retencao_rejeitados', 6)
        for lead in self:
            if excluir:
                self.env['kututa.prospect.exclusion'].create(
                    {
                        'organizacao': lead.partner_name or lead.name,
                        'nif': lead.kp_nif,
                        'email_normalized': lead.email_normalized or lead.email_from,
                        'phone_sanitized': lead.kp_telefone,
                        'cidade': lead.city,
                        'motivo': 'recusou',
                        'profile_id': lead.kp_profile_id.id,
                        'origem_lead_id': lead.id,
                        'company_id': lead.company_id.id or self.env.company.id,
                    }
                )
            with trusted(self.env):
                lead.write(
                    {
                        'kp_verificacao': 'rejeitado',
                        'kp_motivo_rejeicao': motivo,
                        'kp_reter_ate': fields.Date.context_today(self) + timedelta(days=30 * meses),
                    }
                )
            lead.action_archive()
        return True

    def action_kp_rejeitar(self):
        self._kp_verificar_permissao()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Rejeitar lead de prospecção'),
            'res_model': 'kututa.prospect.rejeitar',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lead_ids': self.ids},
        }

    def action_kp_classificar(self):
        self._kp_verificar_permissao()
        self.env['kututa.prospect.ia']._classificar(self, forcar=True)
        return True

    def action_kp_gerar_rascunho(self):
        self._kp_verificar_permissao()
        for lead in self:
            self.env['kututa.prospect.ia']._gerar_rascunho(lead)
        return True

    # ------------------------------------------------------------------ afirmação AGT
    @api.model
    def _kp_texto_agt(self):
        return self.env['ir.config_parameter'].sudo().get_str('kututa_prospect.agt_texto') or ''

    @api.model
    def _kp_validar_afirmacao_agt(self, texto, estado=None):
        """Enquanto o Kututa não estiver homologado, nenhum texto diz que é certificado pela AGT."""
        estado = estado or self.env['ir.config_parameter'].sudo().get_str(
            'kututa_prospect.agt_estado', 'em_homologacao'
        )
        if estado == 'certificado':
            return True
        simples = html2plaintext(texto or '') if '<' in (texto or '') else (texto or '')
        simples = normalizar.sem_acentos(simples).lower()
        padrao = r'certificad.{0,40}agt|agt.{0,40}certificad|homologad.{0,40}agt|agt.{0,40}homologad'
        if re.search(padrao, simples, re.DOTALL):
            raise UserError(
                self.env._(
                    'O Kututa ainda não está homologado pela AGT: o texto não pode dizer que é certificado. Use o '
                    'marcador {{ kututa_agt }}.'
                )
            )
        return True

    def _kp_rascunho_html(self, texto):
        """Texto simples da IA → Html escapado, parágrafo a parágrafo (nunca Html vindo da IA)."""
        paragrafos = [p.strip() for p in texto.split('\n\n') if p.strip()]
        return Markup('').join(Markup('<p>%s</p>') % p for p in paragrafos)

    # ------------------------------------------------------------------ retenção
    @api.model
    def _kp_cron_retencao(self):
        """Termos do Google Places: só o place_id fica sem prazo. Lei 22/11: os rejeitados perdem os contactos."""
        agora = fields.Datetime.now()
        limite_google = agora - timedelta(days=30)
        Lead = self.sudo().with_context(active_test=False)
        candidatos = Lead.search(
            [
                ('kp_profile_id', '!=', False),
                ('kp_verificacao', '!=', 'verificado'),
                ('kp_fonte_ids.fonte', '=', 'google_places'),
                ('kp_fonte_ids.data_recolha', '<', limite_google),
            ]
        )
        # Só os que dependem apenas do Google (um dado confirmado noutra fonte não se apaga).
        so_google = candidatos.filtered(lambda lead: set(lead.kp_fonte_ids.mapped('fonte')) == {'google_places'})
        with trusted(self.env):
            for lead in so_google:
                lead.write(
                    {
                        'name': self.env._('Lugar Google %s', lead.kp_place_id or lead.id),
                        'partner_name': False,
                        'email_from': False,
                        'phone': False,
                        'website': False,
                        'street': False,
                        'city': False,
                        'contact_name': False,
                        'function': False,
                        'kp_rascunho': False,
                        'active': False,
                    }
                )
                lead.kp_fonte_ids.unlink()
            hoje = fields.Date.context_today(self)
            for lead in Lead.search([('kp_reter_ate', '!=', False), ('kp_reter_ate', '<=', hoje)]):
                lead.write(
                    {
                        'email_from': False,
                        'phone': False,
                        'contact_name': False,
                        'function': False,
                        'street': False,
                        'description': False,
                        'kp_rascunho': False,
                        'kp_reter_ate': False,
                    }
                )
        # A caixa de entrada também guarda o que veio do Google: fica só o place_id e o resultado.
        entradas = (
            self.env['kututa.prospect.intake']
            .sudo()
            .search([('create_date', '<', limite_google), ('fontes_json', 'ilike', 'google_places')])
        )
        entradas.write(
            {
                'organizacao': False,
                'nif': False,
                'email': False,
                'telefone': False,
                'website': False,
                'morada': False,
                'cargo_contacto': False,
                'nome_contacto': False,
                'fontes_json': False,
            }
        )
