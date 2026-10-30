from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import email_normalize

from ..tools import normalizar


class KututaProspectExclusion(models.Model):
    _name = 'kututa.prospect.exclusion'
    _description = 'Exclusão global da prospecção'
    _order = 'data desc, id desc'
    _rec_name = 'organizacao'

    company_id = fields.Many2one(
        'res.company', 'Empresa', required=True, default=lambda self: self.env.company, index=True
    )
    organizacao = fields.Char('Organização')
    nif = fields.Char('NIF', index=True)
    email_normalized = fields.Char('E-mail', index=True)
    phone_sanitized = fields.Char('Telefone', index=True)
    cidade = fields.Char()
    chave_nome_cidade = fields.Char('Chave nome e cidade', index=True, readonly=True)
    motivo = fields.Selection(
        [
            ('recusou', 'Recusou o contacto'),
            ('pediu_remocao', 'Pediu para retirar os dados'),
            ('opt_out_email', 'Recusou pelo link do e-mail'),
            ('outro', 'Outro'),
        ],
        required=True,
        default='recusou',
    )
    profile_id = fields.Many2one(
        'kututa.prospect.profile', 'Produto que recusou', help='Só informativo: a exclusão vale para todos.'
    )
    origem_lead_id = fields.Many2one('crm.lead', 'Lead de origem', ondelete='set null')
    data = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    user_id = fields.Many2one('res.users', 'Registada por', default=lambda self: self.env.user, readonly=True)

    @api.model
    def _normalizar(self, vals):
        vals = dict(vals)
        if 'nif' in vals:
            vals['nif'] = normalizar.nif(vals['nif'])
        if 'email_normalized' in vals:
            vals['email_normalized'] = email_normalize(vals['email_normalized'] or '') or False
        if 'phone_sanitized' in vals:
            vals['phone_sanitized'] = normalizar.telefone(vals['phone_sanitized'])
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._normalizar(vals) for vals in vals_list]
        for vals in vals_list:
            vals['chave_nome_cidade'] = normalizar.chave_nome_cidade(vals.get('organizacao'), vals.get('cidade'))
            if not self.env.su:
                vals.update(data=fields.Datetime.now(), user_id=self.env.uid)
        exclusoes = super().create(vals_list)
        exclusoes._sincronizar_listas_de_bloqueio()
        return exclusoes

    def write(self, vals):
        vals = self._normalizar(vals)
        vals.pop('data', None)
        vals.pop('user_id', None)
        res = super().write(vals)
        for exclusao in self:
            exclusao.chave_nome_cidade = normalizar.chave_nome_cidade(exclusao.organizacao, exclusao.cidade)
        self._sincronizar_listas_de_bloqueio()
        return res

    def _sincronizar_listas_de_bloqueio(self):
        """O e-mail entra na mail.blacklist e o telefone na phone.blacklist, para o mass_mailing e o SMS."""
        self.env['crm.lead'].invalidate_model(['kp_excluido'])  # calculado sem guardar: depende desta lista
        for exclusao in self.sudo():
            mensagem = self.env._('Exclusão global da prospecção (%s).', exclusao.organizacao or exclusao.id)
            if exclusao.email_normalized:
                self.env['mail.blacklist'].sudo()._add(exclusao.email_normalized, message=mensagem)
            if exclusao.phone_sanitized:
                self.env['phone.blacklist'].sudo()._add([exclusao.phone_sanitized], message=mensagem)

    @api.model
    def _excluido(self, nif=False, email=False, telefone=False, chave_nome_cidade=False, company=None):
        """Verdadeiro se qualquer chave estiver na exclusão global ou nas listas de bloqueio do Odoo."""
        company = company or self.env.company
        condicoes = []
        if nif:
            condicoes.append([('nif', '=', nif)])
        if email:
            condicoes.append([('email_normalized', '=', email)])
        if telefone:
            condicoes.append([('phone_sanitized', '=', telefone)])
        if chave_nome_cidade:
            condicoes.append([('chave_nome_cidade', '=', chave_nome_cidade)])
        if not condicoes:
            return False
        dominio = Domain('company_id', '=', company.id) & Domain.OR(condicoes)
        if self.sudo().search_count(dominio, limit=1):
            return True
        if email and self.env['mail.blacklist'].sudo().search_count([('email', '=', email)], limit=1):
            return True
        return bool(telefone and self.env['phone.blacklist'].sudo().search_count([('number', '=', telefone)], limit=1))
