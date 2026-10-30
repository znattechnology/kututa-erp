import json
import logging
import os
from collections import namedtuple
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.tools import email_normalize, file_open

_logger = logging.getLogger(__name__)

try:
    import anthropic
except ImportError:  # o módulo declara a dependência; isto só protege o carregamento do registo
    anthropic = None

Resposta = namedtuple('Resposta', ['text', 'handover'])

MODELO = 'claude-opus-5-5'
# Modelos que se podem escolher nas definições. O Haiku não aceita o parâmetro fallbacks (recuperação de recusas).
MODELOS = {
    'claude-opus-5-5': {'nome': 'Opus 5.5 (o mais capaz)', 'fallbacks': True},
    'claude-sonnet-5-5': {'nome': 'Sonnet 5.5 (equilibrado)', 'fallbacks': True},
    'claude-haiku-5-5': {'nome': 'Haiku 5.5 (o mais barato)', 'fallbacks': False},
}
MAX_VOLTAS = 6  # chamadas à API por mensagem do visitante (ferramentas incluídas)
LUANDA = timedelta(hours=1)  # hora de Luanda = UTC+1, sem hora de Verão
SEGMENTOS = {'empresas': 'Empresas', 'escolas': 'Escolas', 'ensino_superior': 'Universidades', 'servicos': 'Serviços'}
VIMEO_NIF = '5003603490'

INDISPONIVEL = (
    'Neste momento não consigo responder. Deixe o seu nome e um e-mail ou telefone nesta conversa e a equipa '
    'da Kututa entra em contacto consigo, ou ligue para +244 923 594 951.'
)
LIMITE = (
    'Esta conversa já vai longa para o assistente automático. Para continuar, a equipa da Kututa vai dar '
    'seguimento pessoalmente: ligue para +244 923 594 951 ou deixe aqui o seu e-mail ou telefone.'
)

FERRAMENTAS = [
    {
        'name': 'registar_contacto',
        'description': (
            'Cria ou actualiza a oportunidade desta conversa no CRM. Chame quando o visitante der o nome e um '
            'e-mail ou telefone, e volte a chamar quando souber mais (empresa, NIF, dimensão, necessidades). '
            'Envie só os campos que conhece.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'nome': {'type': 'string', 'description': 'Nome da pessoa de contacto'},
                'email': {'type': 'string'},
                'telefone': {'type': 'string'},
                'organizacao': {'type': 'string', 'description': 'Nome da empresa, escola ou universidade'},
                'nif': {'type': 'string'},
                'segmento': {'type': 'string', 'enum': ['empresa', 'escola', 'ensino_superior']},
                'dimensao': {
                    'type': 'string',
                    'description': 'Utilizadores, trabalhadores, alunos ou estudantes, em texto livre',
                },
                'sistema_actual': {'type': 'string'},
                'necessidades': {'type': 'string', 'description': 'Resumo do que o visitante precisa'},
            },
            'additionalProperties': False,
        },
    },
    {
        'name': 'consultar_precos',
        'description': (
            'Devolve os planos e serviços da tabela de preços oficial (Kz, sem IVA) de um segmento. '
            'Use sempre antes de falar de preços.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {'segmento': {'type': 'string', 'enum': list(SEGMENTOS)}},
            'required': ['segmento'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'propor_orcamento',
        'description': (
            'Prepara um orçamento em rascunho com produtos da tabela (pela referência, ex.: KUT-NEG, KUT-NEG-IMP) '
            'e quantidades. No pagamento anual, a mensalidade leva quantidade 10. Exige o contacto já registado. '
            'O orçamento fica para aprovação da equipa; não é enviado ao cliente por esta ferramenta.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'linhas': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'referencia': {'type': 'string'},
                            'quantidade': {'type': 'number'},
                        },
                        'required': ['referencia', 'quantidade'],
                        'additionalProperties': False,
                    },
                },
                'observacoes': {'type': 'string'},
            },
            'required': ['linhas'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'marcar_demonstracao',
        'description': (
            'Regista o pedido de demonstração no dia e hora escolhidos pelo visitante (dias úteis, 8h-17h, '
            'hora de Luanda), por confirmar pela equipa. Exige o contacto já registado.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'data_hora': {'type': 'string', 'description': 'AAAA-MM-DDTHH:MM, hora de Luanda'},
                'modalidade': {'type': 'string', 'enum': ['online', 'presencial']},
                'observacoes': {'type': 'string'},
            },
            'required': ['data_hora', 'modalidade'],
            'additionalProperties': False,
        },
    },
    {
        'name': 'passar_para_humano',
        'description': (
            'Pede uma pessoa da equipa para continuar a conversa. Devolve se há alguém disponível agora; se não '
            'houver, a equipa recebe um aviso para contactar o visitante.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {'motivo': {'type': 'string'}},
            'required': ['motivo'],
            'additionalProperties': False,
        },
    },
]


def _ler(nome):
    with file_open(f'kututa_ai_chat/data/{nome}') as f:
        return f.read()


class KututaIaAgente(models.AbstractModel):
    _name = 'kututa.ia.agente'
    _description = 'Agente de IA do chat do site'

    # ------------------------------------------------------------------ conversa
    @api.model
    def _responder(self, channel, texto):
        """Responde a uma mensagem do visitante; devolve o texto e se é para passar a uma pessoa."""
        params = self.env['ir.config_parameter'].sudo()
        if channel.kututa_ia_respostas >= params.get_int('kututa_ia.max_respostas', 30):
            return Resposta(LIMITE, True)
        client = self._cliente()
        if client is None:
            return Resposta(INDISPONIVEL, True)

        modelo = params.get_str('kututa_ia.modelo', MODELO)
        if modelo not in MODELOS:
            modelo = MODELO
        extra = (
            {'betas': ['server-side-fallback-2026-07-01'], 'fallbacks': 'default'}
            if MODELOS[modelo]['fallbacks']
            else {}
        )
        esforco = params.get_str('kututa_ia.esforco', 'low')
        historico = json.loads(channel.kututa_ia_historico or '[]')
        historico.append({'role': 'user', 'content': texto[:4000]})
        estado = {'handover': False}
        resposta = None
        for _volta in range(MAX_VOLTAS):
            try:
                resposta = client.beta.messages.create(
                    model=modelo,
                    max_tokens=16000,
                    system=self._sistema(),
                    tools=FERRAMENTAS,
                    messages=historico,
                    output_config={'effort': esforco},
                    cache_control={'type': 'ephemeral'},
                    metadata={'user_id': f'kututa-canal-{channel.id}'},
                    **extra,
                )
            except Exception as e:  # noqa: BLE001 - qualquer falha da API dá a resposta de indisponível
                _logger.exception('Chat com IA: falha na API (canal %s)', channel.id)
                self._registar_uso(channel, modelo, None, erro=repr(e))
                self._avisar_equipa(channel, 'O assistente de IA falhou nesta conversa; contactar o visitante.')
                channel.kututa_ia_historico = json.dumps(historico)
                return Resposta(INDISPONIVEL, True)
            self._registar_uso(channel, modelo, resposta)
            historico.append({'role': 'assistant', 'content': [b.to_dict(mode='json') for b in resposta.content]})
            if resposta.stop_reason == 'pause_turn':
                continue
            pedidos = [b for b in resposta.content if b.type == 'tool_use']
            if resposta.stop_reason != 'tool_use' or not pedidos:
                break
            resultados = []
            for pedido in pedidos:
                conteudo, erro = self._executar(channel, pedido.name, pedido.input or {}, estado)
                resultados.append(
                    {'type': 'tool_result', 'tool_use_id': pedido.id, 'content': conteudo, 'is_error': erro}
                )
            historico.append({'role': 'user', 'content': resultados})

        channel.kututa_ia_historico = json.dumps(historico)
        channel.kututa_ia_respostas += 1
        texto_final = ''
        if resposta is not None and resposta.stop_reason != 'refusal':
            texto_final = '\n\n'.join(b.text for b in resposta.content if b.type == 'text').strip()
        if not texto_final:
            texto_final = 'Desculpe, não consegui responder a isso. Quer que passe a conversa a uma pessoa da equipa?'
        return Resposta(texto_final, estado['handover'])

    @api.model
    def _cliente(self):
        if anthropic is None or not self.env['ir.config_parameter'].sudo().get_bool('kututa_ia.activo'):
            return None
        chave = os.environ.get('ANTHROPIC_API_KEY')
        if not chave:
            _logger.warning('Chat com IA: falta a variável de ambiente ANTHROPIC_API_KEY')
            return None
        return anthropic.Anthropic(api_key=chave, timeout=60.0, max_retries=2)

    @api.model
    def _sistema(self):
        # Texto fixo (instruções + base de conhecimento) para a cache do prompt funcionar: nada variável aqui.
        return [
            {'type': 'text', 'text': _ler('instrucoes.md')},
            {'type': 'text', 'text': _ler('conhecimento.md'), 'cache_control': {'type': 'ephemeral'}},
        ]

    @api.model
    def _registar_uso(self, channel, modelo, resposta, erro=False):
        vals = {'channel_id': channel.id, 'modelo': modelo, 'erro': erro}
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

    # ------------------------------------------------------------------ ferramentas
    @api.model
    def _executar(self, channel, nome, dados, estado):
        """Executa uma ferramenta; devolve (texto do resultado, é erro). Tudo validado aqui, nunca pela IA."""
        metodo = {
            'registar_contacto': self._registar_contacto,
            'consultar_precos': self._consultar_precos,
            'propor_orcamento': self._propor_orcamento,
            'marcar_demonstracao': self._marcar_demonstracao,
            'passar_para_humano': self._passar_para_humano,
        }.get(nome)
        if not metodo:
            return f'Ferramenta desconhecida: {nome}', True
        try:
            with self.env.cr.savepoint():
                return json.dumps(metodo(channel, dados, estado), ensure_ascii=False), False
        except ValueError as e:
            return str(e), True
        except Exception:  # noqa: BLE001 - o visitante nunca vê detalhes técnicos
            _logger.exception('Chat com IA: erro na ferramenta %s (canal %s)', nome, channel.id)
            return 'Erro interno ao executar a ferramenta.', True

    def _empresa(self):
        empresa = self.env['res.company'].sudo().search([('vat', '=', VIMEO_NIF)], limit=1)
        if not empresa:
            raise ValueError('Ferramenta indisponível nesta base.')
        return empresa

    def _registar_contacto(self, channel, dados, estado):
        empresa = self._empresa()
        email = dados.get('email') and email_normalize(dados['email'])
        if dados.get('email') and not email:
            raise ValueError('O e-mail indicado não é válido; peça ao visitante para o confirmar.')
        detalhes = [
            f'{rotulo}: {dados[campo]}'
            for campo, rotulo in (
                ('segmento', 'Segmento'),
                ('nif', 'NIF'),
                ('dimensao', 'Dimensão'),
                ('sistema_actual', 'Sistema actual'),
                ('necessidades', 'Necessidades'),
            )
            if dados.get(campo)
        ]
        vals = {
            k: v
            for k, v in {
                'contact_name': dados.get('nome'),
                'email_from': email,
                'phone': dados.get('telefone'),
                'partner_name': dados.get('organizacao'),
            }.items()
            if v
        }
        lead = channel.kututa_ia_lead_id.sudo()
        if lead:
            if detalhes:
                vals['description'] = (lead.description or '') + '<br/>' + '<br/>'.join(detalhes)
            lead.write(vals)
        else:
            team = self.env['crm.team'].sudo().search([('company_id', 'in', [empresa.id, False])], limit=1)
            vals.update(
                {
                    'name': f'Chat do site: {dados.get("organizacao") or dados.get("nome") or "visitante"}',
                    'description': '<br/>'.join(detalhes),
                    'origin_channel_id': channel.id,
                    'company_id': empresa.id,
                    'team_id': team.id,
                    'type': 'opportunity',
                    'source_id': self.env.ref('im_livechat.utm_source_chatbot').id,
                }
            )
            lead = self.env['crm.lead'].sudo().create(vals)
            channel.kututa_ia_lead_id = lead
        return {'oportunidade': lead.name, 'registado': True}

    def _consultar_precos(self, channel, dados, estado):
        empresa = self._empresa()
        grupo = SEGMENTOS.get(dados.get('segmento'))
        if not grupo:
            raise ValueError('Segmento inválido.')
        produtos = (
            self.env['product.template']
            .sudo()
            .search(
                [
                    ('default_code', '=like', 'KUT-%'),
                    ('company_id', '=', empresa.id),
                    ('categ_id.name', '=', grupo),
                    ('sale_ok', '=', True),
                ],
                order='default_code',
            )
        )
        return {
            'moeda': 'Kz',
            'iva': 'Preços sem IVA; acresce IVA de 14%',
            'pagamento_anual': 'Paga 10 mensalidades em vez de 12',
            'itens': [
                {
                    'referencia': p.default_code,
                    'nome': p.name,
                    'preco': p.list_price,
                    'unidade': p.uom_id.name,
                    'descricao': p.description_sale or '',
                }
                for p in produtos
            ],
        }

    def _lead_com_contacto(self, channel):
        lead = channel.kututa_ia_lead_id.sudo()
        if not lead or not (lead.email_from or lead.phone):
            raise ValueError('Registe primeiro o contacto (nome e e-mail ou telefone) com registar_contacto.')
        return lead

    def _propor_orcamento(self, channel, dados, estado):
        empresa = self._empresa()
        lead = self._lead_com_contacto(channel)
        orcamentos = self.env['sale.order'].sudo().search_count([('opportunity_id', '=', lead.id)])
        if orcamentos >= 3:
            raise ValueError('Já há 3 orçamentos nesta conversa; passe a conversa a uma pessoa da equipa.')
        linhas = []
        for linha in dados.get('linhas') or []:
            ref = str(linha.get('referencia') or '').strip().upper()
            qtd = linha.get('quantidade')
            if not ref.startswith('KUT-') or not isinstance(qtd, (int, float)) or not 0 < qtd <= 1000:
                raise ValueError(f'Linha inválida: {linha}')
            produto = (
                self.env['product.product']
                .sudo()
                .search([('default_code', '=', ref), ('company_id', '=', empresa.id), ('sale_ok', '=', True)], limit=1)
            )
            if not produto:
                raise ValueError(f'A referência {ref} não existe na tabela; use consultar_precos.')
            linhas.append((0, 0, {'product_id': produto.id, 'product_uom_qty': qtd}))
        if not linhas:
            raise ValueError('O orçamento precisa de pelo menos uma linha.')
        lead._handle_partner_assignment(create_missing=True)
        pricelist = (
            self.env['product.pricelist']
            .sudo()
            .search([('company_id', 'in', [empresa.id, False]), ('currency_id', '=', empresa.currency_id.id)], limit=1)
        )
        order = (
            self.env['sale.order']
            .sudo()
            .with_company(empresa)
            .create(
                {
                    'partner_id': lead.partner_id.id,
                    'opportunity_id': lead.id,
                    'company_id': empresa.id,
                    'pricelist_id': pricelist.id,
                    'origin': 'Chat do site (IA)',
                    'note': dados.get('observacoes') or False,
                    'order_line': linhas,
                }
            )
        )
        order.activity_schedule(
            'mail.mail_activity_data_todo',
            summary='Aprovar proposta preparada pelo chat do site',
            note='Rever as linhas e as quantidades e, se estiver certo, enviar ao cliente por e-mail.',
            user_id=self._responsavel(lead).id,
        )
        return {
            'orcamento': order.name,
            'estado': 'rascunho, para aprovação da equipa',
            'linhas': [
                {'produto': linha.name, 'quantidade': linha.product_uom_qty, 'subtotal': linha.price_subtotal}
                for linha in order.order_line
            ],
            'total_sem_iva': order.amount_untaxed,
            'iva': order.amount_tax,
            'total_com_iva': order.amount_total,
            'moeda': order.currency_id.name,
        }

    def _marcar_demonstracao(self, channel, dados, estado):
        lead = self._lead_com_contacto(channel)
        try:
            local = datetime.strptime(dados.get('data_hora', ''), '%Y-%m-%dT%H:%M')
        except ValueError:
            raise ValueError('Data e hora inválidas; use AAAA-MM-DDTHH:MM.') from None
        agora_local = fields.Datetime.now() + LUANDA  # o Odoo guarda as datas em UTC, sem fuso
        if local < agora_local + timedelta(hours=2):
            raise ValueError('Escolha um dia e hora com pelo menos 2 horas de antecedência.')
        if local.weekday() >= 5 or not 8 <= local.hour <= 16:
            raise ValueError('As demonstrações são em dias úteis, entre as 8h e as 17h (hora de Luanda).')
        inicio = local - LUANDA
        fim = inicio + timedelta(hours=1)
        responsavel = self._responsavel(lead)
        ocupado = (
            self.env['calendar.event']
            .sudo()
            .search_count(
                [('partner_ids', 'in', responsavel.partner_id.ids), ('start', '<', fim), ('stop', '>', inicio)]
            )
        )
        if ocupado:
            raise ValueError('A equipa já tem compromisso a essa hora; proponha outra hora ao visitante.')
        evento = (
            self.env['calendar.event']
            .sudo()
            .create(
                {
                    'name': f'Demonstração Kututa ERP: {lead.partner_name or lead.contact_name} (por confirmar)',
                    'start': inicio,
                    'stop': fim,
                    'user_id': responsavel.id,
                    'partner_ids': [(6, 0, responsavel.partner_id.ids)],
                    'opportunity_id': lead.id,
                    'description': f'Modalidade: {dados.get("modalidade")}. {dados.get("observacoes") or ""}',
                }
            )
        )
        lead.activity_schedule(
            'mail.mail_activity_data_todo',
            summary='Confirmar demonstração pedida no chat do site',
            note=f'{evento.name}, {local:%d/%m/%Y %H:%M} (hora de Luanda), {dados.get("modalidade")}.',
            user_id=responsavel.id,
        )
        return {'registado': True, 'data_hora_luanda': f'{local:%d/%m/%Y %H:%M}', 'estado': 'por confirmar'}

    def _passar_para_humano(self, channel, dados, estado):
        livechat = channel.livechat_channel_id.sudo()
        disponivel = bool(livechat and livechat._get_operator(lang=self.env.context.get('lang')))
        if disponivel:
            estado['handover'] = True
            return {'disponivel': True, 'instrucao': 'Diga numa frase que vai passar a conversa a um colega.'}
        self._avisar_equipa(channel, f'O visitante pediu uma pessoa no chat do site: {dados.get("motivo", "")}')
        return {
            'disponivel': False,
            'instrucao': 'Ninguém está disponível agora. Peça nome e e-mail ou telefone (se ainda não tiver) e '
            'diga que a equipa contacta em breve, ou que pode ligar para +244 923 594 951.',
        }

    def _responsavel(self, lead):
        return lead.user_id or lead.team_id.user_id or self.env.ref('base.user_admin')

    def _avisar_equipa(self, channel, texto):
        try:
            with self.env.cr.savepoint():
                self._criar_aviso(channel, texto)
        except Exception:  # noqa: BLE001 - um aviso que falha nunca impede a resposta ao visitante
            _logger.exception('Chat com IA: não foi possível avisar a equipa (canal %s)', channel.id)

    def _criar_aviso(self, channel, texto):
        lead = channel.kututa_ia_lead_id.sudo()
        if not lead:
            # Sem contacto registado ainda: uma oportunidade mínima ligada à conversa, para a equipa a abrir.
            self._registar_contacto(channel, {}, {})
            lead = channel.kututa_ia_lead_id.sudo()
        lead.activity_schedule(
            'mail.mail_activity_data_todo',
            summary='Chat do site: contactar visitante',
            note=texto,
            user_id=self._responsavel(lead).id,
        )
