import json
import logging
import os

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import file_open, html2plaintext

from ..hooks import VIMEO_NIF
from ..tools.trust import trusted

_logger = logging.getLogger(__name__)

try:
    import anthropic
except ImportError:  # o módulo declara a dependência; isto só protege o carregamento do registo
    anthropic = None

MODELO = 'claude-haiku-5-5'
MODELOS = ('claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5')
POR_VOLTA = 20  # leads classificados por execução do cron
FRASE_RECUSA = 'Se preferir não receber mais contactos nossos, diga-nos e retiramos os seus dados.'
MARCADOR_AGT = '{{ kututa_agt }}'

# Saídas estruturadas da API: os limites numéricos e de tamanho não vão no esquema (não são aceites); valida-os o
# Odoo em _validar_classificacao.
ESQUEMA_CLASSIFICACAO = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['produto_principal', 'produtos_secundarios', 'pontuacoes', 'justificacao', 'dados_em_falta'],
    'properties': {
        'produto_principal': {
            'anyOf': [{'type': 'string'}, {'type': 'null'}],
            'description': 'code de um perfil activo, ou null se nenhum serve',
        },
        'produtos_secundarios': {'type': 'array', 'items': {'type': 'string'}},
        'pontuacoes': {
            'type': 'array',
            'items': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['perfil', 'pontuacao', 'criterios_cumpridos', 'justificacao'],
                'properties': {
                    'perfil': {'type': 'string'},
                    'pontuacao': {'type': 'integer', 'description': 'de 0 a 100'},
                    'criterios_cumpridos': {'type': 'array', 'items': {'type': 'string'}},
                    'justificacao': {'type': 'string'},
                },
            },
        },
        'justificacao': {'type': 'string'},
        'dados_em_falta': {'type': 'array', 'items': {'type': 'string'}},
    },
}
ESQUEMA_RASCUNHO = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['assunto', 'corpo'],
    'properties': {'assunto': {'type': 'string'}, 'corpo': {'type': 'string'}},
}


def _ler(nome):
    with file_open(f'kututa_prospect/data/{nome}') as f:
        return f.read()


class RespostaInvalida(Exception):
    pass


class KututaProspectIa(models.AbstractModel):
    _name = 'kututa.prospect.ia'
    _description = 'Classificação e rascunhos da prospecção com IA'

    @api.model
    def _cliente(self):
        if anthropic is None or not self.env['ir.config_parameter'].sudo().get_bool('kututa_prospect.ia_activa'):
            return None
        chave = os.environ.get('ANTHROPIC_API_KEY')
        if not chave:
            _logger.warning('Prospecção: falta a variável de ambiente ANTHROPIC_API_KEY')
            return None
        return anthropic.Anthropic(api_key=chave, timeout=60.0, max_retries=2)

    @api.model
    def _modelo(self):
        modelo = self.env['ir.config_parameter'].sudo().get_str('kututa_prospect.modelo', MODELO)
        return modelo if modelo in MODELOS else MODELO

    @api.model
    def _registar_uso(self, lead, modelo, resposta, erro=False):
        vals = {'kp_lead_id': lead.id, 'modelo': modelo, 'erro': erro}
        if resposta is not None:
            uso = resposta.usage
            vals.update(
                {
                    'modelo': getattr(resposta, 'model', None) or modelo,
                    'pedido': getattr(resposta, '_request_id', None) or resposta.id,
                    'motivo_paragem': resposta.stop_reason,
                    'tokens_entrada': uso.input_tokens or 0,
                    'tokens_saida': uso.output_tokens or 0,
                    'tokens_cache_lidos': getattr(uso, 'cache_read_input_tokens', 0) or 0,
                    'tokens_cache_escritos': getattr(uso, 'cache_creation_input_tokens', 0) or 0,
                }
            )
        self.env['kututa.ia.uso'].sudo().create(vals)

    @api.model
    def _pedir(self, client, lead, sistema, conteudo, *, esquema, max_tokens):
        """Um pedido com saída JSON; devolve o dicionário ou levanta RespostaInvalida (nada se grava)."""
        modelo = self._modelo()
        try:
            resposta = client.messages.create(
                model=modelo,
                max_tokens=max_tokens,
                system=[{'type': 'text', 'text': sistema, 'cache_control': {'type': 'ephemeral'}}],
                messages=[{'role': 'user', 'content': conteudo}],
                output_config={'effort': 'low', 'format': {'type': 'json_schema', 'schema': esquema}},
                metadata={'user_id': f'kututa-prospect-lead-{lead.id}'},
            )
        except Exception as e:  # noqa: BLE001 - uma falha da API não grava nada
            _logger.exception('Prospecção: falha na API (lead %s)', lead.id)
            self._registar_uso(lead, modelo, None, erro=repr(e))
            raise RespostaInvalida('falha na API') from e
        self._registar_uso(lead, modelo, resposta)
        if resposta.stop_reason in ('max_tokens', 'refusal'):
            raise RespostaInvalida(f'resposta cortada ({resposta.stop_reason})')
        texto = next((b.text for b in resposta.content if b.type == 'text'), '')
        try:
            dados = json.loads(texto)
        except ValueError as e:
            raise RespostaInvalida('JSON inválido') from e
        if not isinstance(dados, dict):
            raise RespostaInvalida('JSON inválido')
        return dados, getattr(resposta, 'model', None) or modelo

    # ------------------------------------------------------------------ dados enviados à IA
    @api.model
    def _perfis_texto(self, perfis):
        blocos = []
        for perfil in perfis:
            criterios = '\n'.join(
                f'  - {c.name} (peso {c.peso}{", obrigatório" if c.obrigatorio else ""})' for c in perfil.criterio_ids
            )
            blocos.append(
                f'<perfil code="{perfil.code}">\nNome: {perfil.name}\nSegmento: {perfil.segmento or ""}\n'
                f'Critérios:\n{criterios}\nDores:\n{perfil.dores or ""}\n</perfil>'
            )
        return '\n'.join(blocos)

    @api.model
    def _lead_texto(self, lead):
        """Só dados institucionais, delimitados: o que vem de sites é dado, não instrução."""
        dados = {
            'organizacao': lead.partner_name or lead.name,
            'cidade': lead.city,
            'morada': lead.street,
            'website': lead.website,
            'tem_email': bool(lead.email_from),
            'dominio_email': (lead.email_from or '').split('@')[-1] if lead.email_from else None,
            'tem_telefone': bool(lead.phone),
            'nif': lead.kp_nif,
            'cargo_publicado': lead.function,
            'notas': html2plaintext(lead.description or '')[:1500] if lead.description else None,
            'fontes': [f'{f.campo}: {f.fonte} ({f.url or "sem URL"})' for f in lead.kp_fonte_ids[:10]],
        }
        return json.dumps({k: v for k, v in dados.items() if v not in (None, False, '', [])}, ensure_ascii=False)

    # ------------------------------------------------------------------ classificação
    @api.model
    def _cron_classificar(self):
        if not self.env['res.company'].sudo().search_count([('vat', '=', VIMEO_NIF)]):
            _logger.warning('Prospecção: esta base não é a da Vímeo; o cron de classificação não corre.')
            return
        leads = (
            self.env['crm.lead']
            .sudo()
            .search(
                [
                    ('kp_profile_id', '!=', False),
                    ('kp_verificacao', '=', 'nao_verificado'),
                    ('kp_classificado_em', '=', False),
                ],
                limit=POR_VOLTA,
                order='id',
            )
        )
        self._classificar(leads)

    @api.model
    def _classificar(self, leads, forcar=False):
        client = self._cliente()
        if client is None:
            if forcar:
                raise UserError(self.env._('A IA da prospecção está desligada ou falta a chave da API no servidor.'))
            return
        perfis = self.env['kututa.prospect.profile']._activos()
        if not perfis:
            return
        sistema = _ler('instrucoes_classificacao.md')
        perfis_texto = self._perfis_texto(perfis)
        for lead in leads.sudo():
            conteudo = (
                f'<perfis>\n{perfis_texto}\n</perfis>\n\n'
                f'<dados_da_organizacao>\n{self._lead_texto(lead)}\n</dados_da_organizacao>'
            )
            try:
                dados, modelo = self._pedir(
                    client, lead, sistema, conteudo, esquema=ESQUEMA_CLASSIFICACAO, max_tokens=4000
                )
                vals = self._validar_classificacao(dados, perfis)
            except RespostaInvalida as e:
                lead.message_post(body=self.env._('A classificação pela IA falhou (%s); nada foi gravado.', e))
                if forcar:
                    raise UserError(self.env._('A classificação pela IA falhou (%s).', e)) from e
                continue
            vals.update(kp_classificado_em=fields.Datetime.now(), kp_modelo_ia=modelo)
            with trusted(self.env):
                lead.write(vals)

    @api.model
    def _validar_classificacao(self, dados, perfis):
        """Nunca se confia na resposta: esquema, códigos activos, limites e critérios obrigatórios."""
        por_codigo = {p.code: p for p in perfis}
        for chave in ESQUEMA_CLASSIFICACAO['required']:
            if chave not in dados:
                raise RespostaInvalida(f'falta «{chave}»')
        if set(dados) - set(ESQUEMA_CLASSIFICACAO['properties']):
            raise RespostaInvalida('campos a mais')
        if not isinstance(dados['pontuacoes'], list) or not isinstance(dados['produtos_secundarios'], list):
            raise RespostaInvalida('tipos inválidos')

        scores, vistos = [], set()
        for item in dados['pontuacoes']:
            if not isinstance(item, dict) or set(item) != {
                'perfil',
                'pontuacao',
                'criterios_cumpridos',
                'justificacao',
            }:
                raise RespostaInvalida('pontuação mal formada')
            perfil = por_codigo.get(item['perfil'])
            if not perfil or perfil.code in vistos:
                continue  # código desconhecido ou repetido: descarta-se
            pontuacao = item['pontuacao']
            if not isinstance(pontuacao, int) or isinstance(pontuacao, bool) or not 0 <= pontuacao <= 100:
                raise RespostaInvalida('pontuação fora de 0 a 100')
            cumpridos = [str(c)[:200] for c in item['criterios_cumpridos'] if isinstance(c, str)][:20]
            obrigatorios = perfil.criterio_ids.filtered('obrigatorio').mapped('name')
            if any(o not in cumpridos for o in obrigatorios):
                pontuacao = min(pontuacao, 30)
            vistos.add(perfil.code)
            scores.append(
                fields.Command.create(
                    {
                        'profile_id': perfil.id,
                        'pontuacao': pontuacao,
                        'criterios_cumpridos': '\n'.join(cumpridos),
                        'justificacao': str(item['justificacao'])[:600],
                    }
                )
            )

        principal = por_codigo.get(dados['produto_principal']) if dados['produto_principal'] else None
        secundarios = []
        for code in dados['produtos_secundarios'][:3]:
            perfil = por_codigo.get(code)
            if perfil and perfil != principal and perfil not in secundarios:
                secundarios.append(perfil)
        vals = {
            'kp_score_ids': [fields.Command.clear(), *scores],
            'kp_justificacao': str(dados['justificacao'])[:1200],
            'kp_produto_secundario_ids': [fields.Command.set([p.id for p in secundarios])],
        }
        if principal:
            vals['kp_produto_principal_id'] = principal.id
        faltam = [str(d)[:100] for d in dados['dados_em_falta'] if isinstance(d, str)][:10]
        if faltam:
            vals['kp_justificacao'] += '\n\nDados em falta: ' + '; '.join(faltam)
        return vals

    # ------------------------------------------------------------------ rascunho
    @api.model
    def _gerar_rascunho(self, lead):
        client = self._cliente()
        if client is None:
            raise UserError(self.env._('A IA da prospecção está desligada ou falta a chave da API no servidor.'))
        lead = lead.sudo()
        perfil = lead.kp_produto_principal_id or lead.kp_profile_id
        canais = [
            nome
            for nome, activo in (
                ('e-mail', perfil.canal_email),
                ('telefone', perfil.canal_telefone),
                ('WhatsApp', perfil.canal_whatsapp),
                ('visita', perfil.canal_visita),
            )
            if activo
        ]
        conteudo = (
            f'<perfil code="{perfil.code}">\nProduto: {perfil.name}\nTom: {perfil.tom}. {perfil.tom_notas or ""}\n'
            f'Cargos: {perfil.cargos or ""}\nDores:\n{perfil.dores or ""}\n'
            f'Proposta de valor:\n{html2plaintext(perfil.proposta_valor or "")}\n'
            f'O que não prometer:\n{perfil.limites or ""}\nCanais: {", ".join(canais)}\n</perfil>\n\n'
            f'<dados_da_organizacao>\n{self._lead_texto(lead)}\n</dados_da_organizacao>'
        )
        try:
            dados, _modelo = self._pedir(
                client, lead, _ler('instrucoes_rascunho.md'), conteudo, esquema=ESQUEMA_RASCUNHO, max_tokens=3000
            )
        except RespostaInvalida as e:
            raise UserError(self.env._('Não foi possível gerar o rascunho (%s).', e)) from e
        assunto = str(dados.get('assunto') or '')[:150].strip()
        corpo = str(dados.get('corpo') or '')[:4000].strip()
        if not assunto or not corpo:
            raise UserError(self.env._('A IA devolveu um rascunho vazio; tente de novo.'))
        if FRASE_RECUSA not in corpo:
            corpo = f'{corpo}\n\n{FRASE_RECUSA}'
        Lead = self.env['crm.lead']
        Lead._kp_validar_afirmacao_agt(f'{assunto}\n{corpo}')
        html = Markup('<p><strong>%s</strong></p>') % assunto + lead._kp_rascunho_html(corpo)
        lead.kp_rascunho = html
        lead.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=self.env._('Rever rascunho da primeira mensagem'),
            user_id=(lead.user_id or self.env.user).id,
        )
        return True
