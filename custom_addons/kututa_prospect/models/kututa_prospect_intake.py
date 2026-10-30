import json
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import email_normalize

from ..hooks import VIMEO_NIF
from ..tools import normalizar
from ..tools.trust import trusted
from .kututa_prospect_profile import FONTES, PROVINCIAS

_logger = logging.getLogger(__name__)

MAX_POR_CHAMADA = 50
# Domínios de correio pessoal: um e-mail destes não é institucional.
CORREIO_PESSOAL = {'gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'live.com', 'icloud.com', 'ymail.com'}
ESTADOS = [
    ('pendente', 'Pendente'),
    ('criado', 'Lead criado'),
    ('duplicado', 'Duplicado (lead existente actualizado)'),
    ('excluido', 'Excluído'),
    ('rejeitado', 'Rejeitado'),
    ('erro', 'Erro'),
]
CAMPOS_ENTRADA = {
    'profile_code',
    'query_id',
    'organizacao',
    'nif',
    'email',
    'telefone',
    'website',
    'morada',
    'cidade',
    'provincia',
    'cargo_contacto',
    'nome_contacto',
    'place_id',
    'fontes_json',
}


class KututaProspectIntake(models.Model):
    _name = 'kututa.prospect.intake'
    _description = 'Entrada de prospecção vinda do n8n'
    _order = 'id desc'
    _rec_name = 'organizacao'

    company_id = fields.Many2one('res.company', 'Empresa', required=True, index=True, readonly=True)
    profile_code = fields.Char('Perfil', required=True, readonly=True)
    query_id = fields.Many2one('kututa.prospect.query', 'Consulta', readonly=True, ondelete='set null')
    organizacao = fields.Char('Organização', readonly=True)
    nif = fields.Char('NIF', readonly=True)
    email = fields.Char('E-mail', readonly=True)
    telefone = fields.Char(readonly=True)
    website = fields.Char(readonly=True)
    morada = fields.Char(readonly=True)
    cidade = fields.Char(readonly=True)
    provincia = fields.Selection(PROVINCIAS, 'Província', readonly=True)
    cargo_contacto = fields.Char('Cargo do contacto', readonly=True)
    nome_contacto = fields.Char('Nome do contacto', readonly=True)
    place_id = fields.Char('Google place_id', readonly=True, index=True)
    fontes_json = fields.Text('Fontes (JSON)', readonly=True)
    estado = fields.Selection(ESTADOS, default='pendente', required=True, readonly=True, index=True)
    lead_id = fields.Many2one('crm.lead', readonly=True, ondelete='set null')
    mensagem = fields.Char('Motivo', readonly=True)

    # ------------------------------------------------------------------ entrada
    @api.model_create_multi
    def create(self, vals_list):
        if len(vals_list) > MAX_POR_CHAMADA:
            raise ValidationError(self.env._('No máximo %s entradas por chamada.', MAX_POR_CHAMADA))
        empresa = self.env['res.company'].sudo().search([('vat', '=', VIMEO_NIF)], limit=1)
        if not empresa:
            raise UserError(self.env._('A prospecção só funciona no Odoo interno da Vímeo.'))
        self._verificar_limite_diario(len(vals_list))
        # Só os dados da entrada; o estado, o lead e o motivo são do servidor, venham ou não no pedido.
        limpos = [
            dict({k: v for k, v in vals.items() if k in CAMPOS_ENTRADA}, company_id=empresa.id, estado='pendente')
            for vals in vals_list
        ]
        for vals in limpos:
            if vals.get('provincia') not in dict(PROVINCIAS):
                vals.pop('provincia', None)
        entradas = super().create(limpos)
        for entrada in entradas.sudo():
            try:
                with self.env.cr.savepoint():
                    entrada._processar()
            except Exception as e:  # noqa: BLE001 - uma entrada má não pode travar o lote do n8n
                _logger.exception('Prospecção: erro ao processar a entrada %s', entrada.id)
                entrada.write({'estado': 'erro', 'mensagem': str(e)[:200]})
        return entradas

    def _verificar_limite_diario(self, novas):
        if self.env.su:
            return
        maximo = self.env['ir.config_parameter'].sudo().get_int('kututa_prospect.max_entradas_dia', 2000)
        hoje = self.sudo().search_count(
            [('create_uid', '=', self.env.uid), ('create_date', '>=', fields.Datetime.now() - timedelta(days=1))]
        )
        if maximo and hoje + novas > maximo:
            raise ValidationError(self.env._('Limite diário de %s entradas atingido.', maximo))

    # ------------------------------------------------------------------ processamento
    def _fontes(self):
        """Lista validada de fontes [{campo, url, fonte, data}]; vazia se o JSON for inválido."""
        try:
            fontes = json.loads(self.fontes_json or '[]')
        except ValueError:
            return []
        if not isinstance(fontes, list):
            return []
        validas = []
        for fonte in fontes[:30]:
            if not isinstance(fonte, dict):
                continue
            url = str(fonte.get('url') or '')[:500]
            tipo = fonte.get('fonte')
            if not url.startswith(('https://', 'http://')) or tipo not in dict(FONTES):
                continue
            validas.append(
                {
                    'campo': str(fonte.get('campo') or 'organização')[:60],
                    'url': url,
                    'fonte': tipo,
                    'data_recolha': self._data(fonte.get('data')),
                }
            )
        return validas

    @api.model
    def _data(self, valor):
        try:
            data = fields.Datetime.to_datetime(str(valor)[:19].replace('T', ' ')) if valor else None
        except ValueError:
            data = None
        agora = fields.Datetime.now()
        return data if data and data <= agora else agora

    def _rejeitar(self, estado, mensagem, lead=None):
        self.write({'estado': estado, 'mensagem': mensagem, 'lead_id': lead.id if lead else False})

    def _processar(self):  # noqa: PLR0911 - cada regra de rejeição sai cedo, com o seu motivo
        self.ensure_one()
        perfil = self.env['kututa.prospect.profile'].search(
            [('code', '=', self.profile_code), ('active', '=', True), ('company_id', '=', self.company_id.id)],
            limit=1,
        )
        if not perfil:
            return self._rejeitar('rejeitado', 'Perfil inexistente ou inactivo.')
        fontes = self._fontes()
        if not fontes:
            return self._rejeitar('rejeitado', 'Sem fontes válidas: cada entrada precisa de pelo menos um URL.')
        organizacao = (self.organizacao or '').strip()[:200]
        if not organizacao:
            return self._rejeitar('rejeitado', 'Falta o nome da organização.')
        email = email_normalize(self.email or '') or False
        if self.email and not email:
            return self._rejeitar('rejeitado', 'E-mail inválido.')
        if email and email.split('@')[1] in CORREIO_PESSOAL:
            return self._rejeitar('rejeitado', 'O e-mail não é institucional.')
        nif = normalizar.nif(self.nif)
        telefone = normalizar.telefone(self.telefone)
        chave_nc = normalizar.chave_nome_cidade(organizacao, self.cidade)

        Exclusao = self.env['kututa.prospect.exclusion']
        if Exclusao._excluido(nif, email, telefone, chave_nc, company=self.company_id):
            # O n8n só fica a saber que foi excluído, não porquê.
            return self._rejeitar('excluido', 'Excluído.')

        cliente = nif and self.env['res.partner'].search(
            [('vat', '=', nif), ('customer_rank', '>', 0), ('company_id', 'in', [self.company_id.id, False])],
            limit=1,
        )
        if cliente:
            cliente.message_post(
                body=self.env._(
                    'A prospecção (%s) voltou a encontrar este cliente: oportunidade de venda cruzada.', perfil.name
                )
            )
            return self._rejeitar('duplicado', 'Já é cliente.')

        existente = self._procurar_duplicado(
            nif, email, telefone, normalizar.chave_dedup(nif, telefone, organizacao, self.cidade)
        )
        if existente:
            if existente.won_status == 'won':
                existente.message_post(
                    body=self.env._(
                        'A prospecção (%s) voltou a encontrar este cliente: oportunidade de venda cruzada.',
                        perfil.name,
                    )
                )
                return self._rejeitar('duplicado', 'Já é cliente.', existente)
            self._juntar(existente, fontes, nif, email)
            return self._rejeitar('duplicado', 'Lead existente actualizado.', existente)

        lead_vals = {
            'name': self.env._('%(org)s (%(perfil)s)', org=organizacao, perfil=perfil.name),
            'partner_name': organizacao,
            'kp_profile_id': perfil.id,
            'kp_produto_principal_id': perfil.id,
            'kp_nif': nif,
            'kp_place_id': (self.place_id or '')[:200] or False,
            'email_from': email,
            'phone': telefone or False,
            'website': self._url(self.website),
            'street': (self.morada or '')[:200] or False,
            'city': (self.cidade or '')[:100] or False,
            'country_id': self.env.ref('base.ao').id,
            'contact_name': (self.nome_contacto or '')[:100] or False,
            'function': (self.cargo_contacto or '')[:100] or False,
            'company_id': self.company_id.id,
            'user_id': False,  # sem vendedor até alguém o verificar (quem verifica fica com ele)
            'source_id': self.env.ref('kututa_prospect.utm_source_n8n').id,
            'kp_fonte_ids': [fields.Command.create(f) for f in fontes],
        }
        with trusted(self.env):
            lead = self.env['crm.lead'].create(lead_vals)
        if self.query_id:
            self.query_id.ultima_execucao = fields.Datetime.now()
        self._rejeitar('criado', 'Lead criado.', lead)
        return True

    @api.model
    def _url(self, valor):
        valor = (valor or '').strip()[:300]
        return valor if valor.startswith(('https://', 'http://')) else False

    def _procurar_duplicado(self, nif, email, telefone, chave):
        Lead = self.env['crm.lead'].with_context(active_test=False)
        condicoes = [('kp_dedup_key', '=', chave)] if chave else []
        if self.place_id:
            condicoes.append(('kp_place_id', '=', self.place_id))
        if nif:
            condicoes.append(('kp_nif', '=', nif))
        if telefone:
            condicoes.append(('kp_telefone', '=', telefone))
        if email:
            condicoes.append(('email_normalized', '=', email))
        if not condicoes:
            return Lead
        dominio = ['|'] * (len(condicoes) - 1) + condicoes
        limite_perdidos = fields.Datetime.now() - timedelta(days=365)
        candidatos = Lead.search(
            [('company_id', 'in', [self.company_id.id, False])] + dominio, order='active desc, id desc', limit=10
        )
        # Activos, ou perdidos/rejeitados há menos de 12 meses.
        return candidatos.filtered(lambda lead: lead.active or lead.write_date >= limite_perdidos)[:1]

    def _juntar(self, lead, fontes, nif, email):
        """Junta as fontes novas e preenche os campos vazios, sem sobrescrever o que uma pessoa já verificou."""
        urls = set(lead.kp_fonte_ids.mapped(lambda f: (f.campo, f.url)))
        novas = [f for f in fontes if (f['campo'], f['url']) not in urls]
        vals = {}
        if lead.kp_verificacao != 'verificado':
            preencher = {
                'kp_nif': nif,
                'email_from': email,
                'phone': normalizar.telefone(self.telefone),
                'website': self._url(self.website),
                'street': self.morada,
                'city': self.cidade,
                'kp_place_id': self.place_id,
            }
            vals = {k: v for k, v in preencher.items() if v and not lead[k]}
        with trusted(self.env):
            if novas:
                vals['kp_fonte_ids'] = [fields.Command.create(f) for f in novas]
            if vals:
                lead.write(vals)
