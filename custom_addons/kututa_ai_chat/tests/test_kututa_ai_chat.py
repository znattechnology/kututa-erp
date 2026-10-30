import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from ..models import kututa_ia_agente as agente_mod


class Bloco(SimpleNamespace):
    def to_dict(self, mode='python'):
        return dict(vars(self))


def texto(t):
    return Bloco(type='text', text=t)


def ferramenta(nome, dados, ident='toolu_1'):
    return Bloco(type='tool_use', id=ident, name=nome, input=dados)


def resposta(blocos, stop='end_turn'):
    uso = SimpleNamespace(
        input_tokens=1000, output_tokens=200, cache_read_input_tokens=15000, cache_creation_input_tokens=0
    )
    return SimpleNamespace(id='msg_1', model='claude-opus-5-5', content=blocos, stop_reason=stop, usage=uso)


class ClienteFalso:
    """Simula anthropic.Anthropic(): devolve as respostas pela ordem e guarda os pedidos."""

    def __init__(self, respostas, erro=None):
        self.respostas = list(respostas)
        self.pedidos = []
        self.erro = erro
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.pedidos.append(json.loads(json.dumps(kwargs, default=str)))
        if self.erro:
            raise self.erro
        return self.respostas.pop(0)


@tagged('post_install', '-at_install')
class TestKututaAiChat(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.empresa = cls.env.company
        cls.empresa.vat = agente_mod.VIMEO_NIF
        cls.agente = cls.env['kututa.ia.agente']
        Cat = cls.env['product.category']
        raiz = Cat.create({'name': 'Kututa ERP'})
        empresas = Cat.create({'name': 'Empresas', 'parent_id': raiz.id})
        for ref, nome, preco in (
            ('KUT-NEG', 'Kututa ERP Negócio (mensalidade)', 55000),
            ('KUT-NEG-IMP', 'Implementação Negócio', 350000),
        ):
            cls.env['product.template'].create(
                {
                    'name': nome,
                    'default_code': ref,
                    'list_price': preco,
                    'type': 'service',
                    'categ_id': empresas.id,
                    'company_id': cls.empresa.id,
                    'taxes_id': [(5, 0, 0)],
                }
            )
        cls.canal = cls.env['discuss.channel'].create({'name': 'Visitante', 'channel_type': 'group'})

    def _com(self, cliente):
        return patch.object(type(self.agente), '_cliente', lambda self_: cliente)

    def test_conversa_simples_regista_historico_e_custo(self):
        cliente = ClienteFalso([resposta([texto('Olá! Sou o Assistente Kututa.')])])
        with self._com(cliente):
            r = self.agente._responder(self.canal, 'Bom dia')
        self.assertEqual(r.text, 'Olá! Sou o Assistente Kututa.')
        self.assertFalse(r.handover)
        pedido = cliente.pedidos[0]
        self.assertEqual(pedido['model'], 'claude-opus-5-5')
        self.assertEqual(pedido['fallbacks'], 'default')
        self.assertEqual(pedido['output_config'], {'effort': 'low'})
        # A base de conhecimento vai no sistema, com cache; nada variável lá dentro.
        self.assertIn('cache_control', pedido['system'][-1])
        self.assertIn('Kututa ERP', pedido['system'][-1]['text'])
        historico = json.loads(self.canal.kututa_ia_historico)
        self.assertEqual([m['role'] for m in historico], ['user', 'assistant'])
        self.assertEqual(self.canal.kututa_ia_respostas, 1)
        uso = self.canal.kututa_ia_uso_ids
        self.assertEqual(len(uso), 1)
        self.assertAlmostEqual(uso.custo_usd, (1000 * 4 + 200 * 20 + 15000 * 0.20) / 1e6, places=6)

    def test_ferramentas_ate_ao_orcamento_com_precos_do_odoo(self):
        cliente = ClienteFalso(
            [
                resposta(
                    [
                        ferramenta(
                            'registar_contacto',
                            {'nome': 'Ana Teste', 'email': 'ana@exemplo.ao', 'organizacao': 'Loja Teste'},
                            'toolu_a',
                        )
                    ],
                    stop='tool_use',
                ),
                resposta(
                    [
                        ferramenta(
                            'propor_orcamento',
                            {
                                'linhas': [
                                    {'referencia': 'kut-neg', 'quantidade': 10, 'preco': 1},
                                    {'referencia': 'KUT-NEG-IMP', 'quantidade': 1},
                                ]
                            },
                            'toolu_b',
                        )
                    ],
                    stop='tool_use',
                ),
                resposta([texto('Preparei a proposta; a equipa vai revê-la e enviá-la por e-mail.')]),
            ]
        )
        with self._com(cliente):
            r = self.agente._responder(self.canal, 'Quero uma proposta do plano Negócio, pagamento anual')
        self.assertIn('Preparei a proposta', r.text)
        lead = self.canal.kututa_ia_lead_id
        self.assertEqual(
            (lead.contact_name, lead.email_from, lead.origin_channel_id), ('Ana Teste', 'ana@exemplo.ao', self.canal)
        )
        order = self.env['sale.order'].search([('opportunity_id', '=', lead.id)])
        self.assertEqual(order.state, 'draft')
        # Preços sempre do Odoo, nunca do que a IA escreveu.
        self.assertEqual(order.amount_untaxed, 10 * 55000 + 350000)
        self.assertTrue(order.activity_ids)
        resultado = json.loads(cliente.pedidos[2]['messages'][-1]['content'][0]['content'])
        self.assertEqual(resultado['total_sem_iva'], 900000)
        self.assertEqual(len(cliente.pedidos), 3)

    def test_referencia_inventada_e_recusada(self):
        cliente = ClienteFalso(
            [
                resposta([ferramenta('registar_contacto', {'nome': 'Rui', 'telefone': '923000000'})], stop='tool_use'),
                resposta(
                    [ferramenta('propor_orcamento', {'linhas': [{'referencia': 'PROMO-50', 'quantidade': 1}]}, 'x')],
                    stop='tool_use',
                ),
                resposta([texto('Não encontrei esse produto.')]),
            ]
        )
        with self._com(cliente):
            self.agente._responder(self.canal, 'Quero o produto PROMO-50')
        ultimo = cliente.pedidos[2]['messages'][-1]['content'][0]
        self.assertTrue(ultimo['is_error'])
        self.assertFalse(self.env['sale.order'].search([('opportunity_id', '=', self.canal.kututa_ia_lead_id.id)]))

    def test_orcamento_exige_contacto(self):
        conteudo, erro = self.agente._executar(
            self.canal, 'propor_orcamento', {'linhas': [{'referencia': 'KUT-NEG', 'quantidade': 1}]}, {}
        )
        self.assertTrue(erro)
        self.assertIn('registar_contacto', conteudo)

    def test_precos_so_da_tabela_da_vimeo(self):
        conteudo, erro = self.agente._executar(self.canal, 'consultar_precos', {'segmento': 'empresas'}, {})
        self.assertFalse(erro)
        refs = [i['referencia'] for i in json.loads(conteudo)['itens']]
        self.assertEqual(refs, ['KUT-NEG', 'KUT-NEG-IMP'])

    def test_ferramentas_recusam_noutra_empresa(self):
        self.empresa.vat = '5000004251'
        conteudo, erro = self.agente._executar(self.canal, 'consultar_precos', {'segmento': 'empresas'}, {})
        self.assertTrue(erro)

    def test_demonstracao_valida_e_em_dia_util(self):
        self.agente._executar(self.canal, 'registar_contacto', {'nome': 'Rui', 'email': 'rui@exemplo.ao'}, {})
        hoje = fields.Date.today()
        sabado = hoje + timedelta(days=(5 - hoje.weekday()) % 7 or 7)
        conteudo, erro = self.agente._executar(
            self.canal, 'marcar_demonstracao', {'data_hora': f'{sabado}T10:00', 'modalidade': 'online'}, {}
        )
        self.assertTrue(erro)
        segunda = sabado + timedelta(days=2)
        conteudo, erro = self.agente._executar(
            self.canal, 'marcar_demonstracao', {'data_hora': f'{segunda}T10:00', 'modalidade': 'online'}, {}
        )
        self.assertFalse(erro, conteudo)
        evento = self.env['calendar.event'].search([('opportunity_id', '=', self.canal.kututa_ia_lead_id.id)])
        self.assertEqual(evento.start, fields.Datetime.to_datetime(f'{segunda} 09:00:00'))  # 10h Luanda = 9h UTC

    def test_limite_de_respostas(self):
        self.canal.kututa_ia_respostas = 30
        cliente = ClienteFalso([])
        with self._com(cliente):
            r = self.agente._responder(self.canal, 'Mais uma pergunta')
        self.assertTrue(r.handover)
        self.assertFalse(cliente.pedidos)

    def test_falha_da_api_responde_e_avisa_equipa(self):
        cliente = ClienteFalso([], erro=RuntimeError('rede'))
        with self._com(cliente), mute_logger('odoo.addons.kututa_ai_chat.models.kututa_ia_agente'):
            r = self.agente._responder(self.canal, 'Olá')
        self.assertEqual(r.text, agente_mod.INDISPONIVEL)
        self.assertTrue(self.canal.kututa_ia_lead_id.activity_ids)
        self.assertTrue(self.canal.kututa_ia_uso_ids.erro)

    def test_sem_chave_fica_indisponivel(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': ''}):
            r = self.agente._responder(self.canal, 'Olá')
        self.assertEqual(r.text, agente_mod.INDISPONIVEL)

    def test_passo_de_ia_nao_avanca_no_guiao(self):
        passo = self.env.ref('kututa_ai_chat.chatbot_kututa_ia_passo')
        self.assertEqual(passo._process_answer(self.canal, '<p>Olá</p>'), passo)

    def test_modelo_escolhido_nas_definicoes(self):
        definicoes = self.env['res.config.settings'].create(
            {'kututa_ia_modelo': 'claude-haiku-5-5', 'kututa_ia_esforco': 'medium'}
        )
        definicoes.execute()
        cliente = ClienteFalso([resposta([texto('Olá!')])])
        with self._com(cliente):
            self.agente._responder(self.canal, 'Olá')
        pedido = cliente.pedidos[0]
        self.assertEqual(pedido['model'], 'claude-haiku-5-5')
        self.assertEqual(pedido['output_config'], {'effort': 'medium'})
        # O Haiku não aceita a recuperação de recusas: o pedido vai sem fallbacks.
        self.assertNotIn('fallbacks', pedido)
        self.assertEqual(pedido['betas'], ['thinking-binding-controls-2026-08-01'])
        # Raciocínio de instruções antigas ou de outro modelo é descartado, não faz falhar a conversa.
        self.assertEqual(pedido['thinking']['block_binding'], {'prefix_mismatch_behavior': 'drop_block'})

    def test_sonnet_leva_fallbacks_e_modelo_invalido_volta_ao_opus(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_str('kututa_ia.modelo', 'claude-sonnet-5-5')
        cliente = ClienteFalso([resposta([texto('a')]), resposta([texto('b')])])
        with self._com(cliente):
            self.agente._responder(self.canal, 'Olá')
            params.set_str('kututa_ia.modelo', 'modelo-que-nao-existe')
            self.agente._responder(self.canal, 'Outra')
        self.assertEqual(cliente.pedidos[0]['model'], 'claude-sonnet-5-5')
        self.assertEqual(cliente.pedidos[0]['fallbacks'], 'default')
        self.assertEqual(cliente.pedidos[1]['model'], 'claude-opus-5-5')

    def test_desligado_nas_definicoes(self):
        self.env['res.config.settings'].create({'kututa_ia_activo': False}).execute()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'chave-de-teste'}):
            r = self.agente._responder(self.canal, 'Olá')
        self.assertEqual(r.text, agente_mod.INDISPONIVEL)
