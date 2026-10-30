import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from .. import hooks
from ..models import kututa_prospect_ia as ia_mod


def resposta(dados, stop='end_turn'):
    texto = dados if isinstance(dados, str) else json.dumps(dados)
    uso = SimpleNamespace(
        input_tokens=1500, output_tokens=300, cache_read_input_tokens=0, cache_creation_input_tokens=0
    )
    bloco = SimpleNamespace(type='text', text=texto)
    return SimpleNamespace(id='msg_1', model='claude-haiku-5-5', content=[bloco], stop_reason=stop, usage=uso)


class ClienteFalso:
    """Simula anthropic.Anthropic(): devolve as respostas pela ordem e guarda os pedidos."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.pedidos.append(json.loads(json.dumps(kwargs, default=str)))
        return self.respostas.pop(0)


def classificacao(principal='escolas', pontuacao=80, cumpridos=None, **extra):
    dados = {
        'produto_principal': principal,
        'produtos_secundarios': ['empresas'],
        'pontuacoes': [
            {
                'perfil': 'escolas',
                'pontuacao': pontuacao,
                'criterios_cumpridos': ['Escola privada ou comparticipada', 'Mais de 200 alunos']
                if cumpridos is None
                else cumpridos,
                'justificacao': 'Colégio privado com site institucional.',
            },
            {'perfil': 'empresas', 'pontuacao': 20, 'criterios_cumpridos': [], 'justificacao': 'Venda cruzada.'},
        ],
        'justificacao': 'Serve sobretudo para a gestão escolar.',
        'dados_em_falta': ['Número de alunos'],
    }
    dados.update(extra)
    return dados


@tagged('post_install', '-at_install', 'prospect')
class TestKututaProspect(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.empresa = cls.env.company
        cls.empresa.vat = hooks.VIMEO_NIF
        cls.env['ir.config_parameter'].sudo().set_bool('kututa_prospect.ia_activa', True)
        cls.equipa = cls.env.ref('sales_team.team_sales_department')
        cls.outra_equipa = cls.env['crm.team'].create({'name': 'Outra equipa'})
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.vendedor = Users.create(
            {
                'name': 'Vendedor Prospecção',
                'login': 'vendedor.prospect@teste.ao',
                'group_ids': [Command.set([cls.env.ref('kututa_prospect.group_prospect_user').id])],
            }
        )
        cls.outro_vendedor = Users.create(
            {
                'name': 'Vendedor de outra equipa',
                'login': 'outro.prospect@teste.ao',
                'group_ids': [
                    Command.set(
                        [
                            cls.env.ref('kututa_prospect.group_prospect_user').id,
                            cls.env.ref('sales_team.group_sale_salesman_all_leads').id,
                        ]
                    )
                ],
            }
        )
        cls.env['crm.team.member'].create({'crm_team_id': cls.equipa.id, 'user_id': cls.vendedor.id})
        cls.env['crm.team.member'].create({'crm_team_id': cls.outra_equipa.id, 'user_id': cls.outro_vendedor.id})
        cls.n8n = cls.env.ref('kututa_prospect.user_n8n')
        cls.escolas = cls.env.ref('kututa_prospect.profile_escolas')
        cls.revisao = cls.env.ref('kututa_prospect.stage_para_rever')
        cls.ia = cls.env['kututa.prospect.ia']

    def _entrada(self, **vals):
        dados = {
            'profile_code': 'escolas',
            'organizacao': 'Colégio Esperança',
            'cidade': 'Luanda',
            'telefone': '923 000 111',
            'email': 'geral@colegioesperanca.ao',
            'website': 'https://colegioesperanca.ao',
            'place_id': 'ChIJteste1',
            'fontes_json': json.dumps(
                [{'campo': 'organização', 'url': 'https://colegioesperanca.ao', 'fonte': 'site_organizacao'}]
            ),
        }
        dados.update(vals)
        # Lê-se o resultado como administrador: o n8n não vê leads.
        return self.env['kututa.prospect.intake'].with_user(self.n8n).create(dados).with_env(self.env)

    def _com(self, cliente):
        return patch.object(type(self.ia), '_cliente', lambda self_: cliente)

    # ------------------------------------------------------------------ caixa de entrada
    def test_entrada_cria_lead_por_verificar_em_para_rever(self):
        entrada = self._entrada()
        self.assertEqual(entrada.estado, 'criado')
        lead = entrada.lead_id
        self.assertEqual(lead.kp_profile_id, self.escolas)
        self.assertEqual(lead.kp_verificacao, 'nao_verificado')
        self.assertEqual(lead.stage_id, self.revisao)
        self.assertEqual(lead.team_id, self.equipa)
        self.assertEqual(lead.kp_telefone, '+244923000111')
        self.assertEqual(lead.kp_dedup_key, 'tel:+244923000111')
        self.assertEqual(lead.kp_fonte_ids.fonte, 'site_organizacao')
        self.assertEqual(lead.source_id, self.env.ref('kututa_prospect.utm_source_n8n'))

    def test_entrada_rejeitada_sem_fontes_perfil_inactivo_ou_email_pessoal(self):
        self.assertEqual(self._entrada(fontes_json='[]').estado, 'rejeitado')
        self.assertEqual(self._entrada(fontes_json='isto não é JSON').estado, 'rejeitado')
        sem_url = json.dumps([{'campo': 'nome', 'url': 'javascript:alert(1)', 'fonte': 'google_places'}])
        self.assertEqual(self._entrada(fontes_json=sem_url).estado, 'rejeitado')
        rede_social = json.dumps([{'campo': 'nome', 'url': 'https://facebook.com/x', 'fonte': 'facebook'}])
        self.assertEqual(self._entrada(fontes_json=rede_social).estado, 'rejeitado')
        self.assertEqual(self._entrada(email='director@gmail.com').estado, 'rejeitado')
        self.env.ref('kututa_prospect.profile_universidade').active = False
        self.assertEqual(self._entrada(profile_code='universidade').estado, 'rejeitado')
        self.assertEqual(self._entrada(profile_code='nao_existe').estado, 'rejeitado')

    def test_entrada_ignora_estado_e_lead_forjados(self):
        alheio = self.env['crm.lead'].create({'name': 'Lead alheio'})
        entrada = self._entrada(estado='criado', lead_id=alheio.id, mensagem='ok', fontes_json='[]')
        self.assertEqual(entrada.estado, 'rejeitado')
        self.assertNotEqual(entrada.lead_id, alheio)

    def test_deduplicacao_pelas_cinco_chaves(self):
        lead = self._entrada(nif='5000-111 222').lead_id
        casos = {
            'nif': {'nif': '5000111222', 'telefone': False, 'email': False, 'place_id': False},
            'telefone': {'telefone': '+244 923 000 111', 'email': False, 'place_id': False},
            'email': {'email': 'GERAL@colegioesperanca.ao', 'telefone': False, 'place_id': False},
            'place_id': {'telefone': False, 'email': False, 'organizacao': 'Outro nome'},
        }
        for chave, vals in casos.items():
            with self.subTest(chave=chave):
                entrada = self._entrada(**vals)
                self.assertEqual(entrada.estado, 'duplicado')
                self.assertEqual(entrada.lead_id, lead)
        lead2 = self._entrada(
            organizacao='Colégio Sol Nascente, Lda', cidade='Benguela', telefone=False, email=False, place_id=False
        ).lead_id
        entrada = self._entrada(
            organizacao='colegio sol nascente', cidade='benguela', telefone=False, email=False, place_id=False
        )
        self.assertEqual(entrada.estado, 'duplicado')
        self.assertEqual(entrada.lead_id, lead2)

    def test_duplicado_junta_fontes_sem_sobrescrever_dados_verificados(self):
        lead = self._entrada().lead_id
        lead.with_user(self.vendedor).action_kp_verificar()
        nova = json.dumps([{'campo': 'telefone', 'url': 'https://lista.med.gov.ao/x', 'fonte': 'lista_med'}])
        self._entrada(website='https://outro.ao', fontes_json=nova)
        self.assertEqual(lead.website, 'https://colegioesperanca.ao')
        self.assertIn('lista_med', lead.kp_fonte_ids.mapped('fonte'))

    def test_limites_por_chamada(self):
        Intake = self.env['kututa.prospect.intake'].with_user(self.n8n)
        with self.assertRaises(ValidationError):
            Intake.create([{'profile_code': 'escolas'}] * 51)
        self.env['ir.config_parameter'].sudo().set_int('kututa_prospect.max_entradas_dia', 2)
        self._entrada()
        with self.assertRaises(ValidationError):
            Intake.create([{'profile_code': 'escolas'}] * 2)

    # ------------------------------------------------------------------ exclusão
    def test_exclusao_bloqueia_entrada_e_criacao_manual(self):
        Exclusao = self.env['kututa.prospect.exclusion'].with_user(self.vendedor)
        Exclusao.create({'organizacao': 'Colégio Esperança', 'email_normalized': 'Geral@ColegioEsperanca.ao'})
        self.assertTrue(self.env['mail.blacklist'].search_count([('email', '=', 'geral@colegioesperanca.ao')]))
        entrada = self._entrada()
        self.assertEqual(entrada.estado, 'excluido')
        self.assertFalse(entrada.lead_id)
        self.assertEqual(entrada.mensagem, 'Excluído.')  # o n8n não fica a saber porquê
        for vals in (
            {'email_from': 'geral@colegioesperanca.ao'},
            {'partner_name': 'COLÉGIO ESPERANÇA, LDA', 'city': 'luanda', 'email_from': False},
        ):
            if 'city' in vals:
                Exclusao.create({'organizacao': 'Colégio Esperança', 'cidade': 'Luanda'})
            with self.subTest(vals=vals), self.assertRaises(UserError):
                self.env['crm.lead'].with_user(self.vendedor).create(
                    dict({'name': 'Manual', 'kp_profile_id': self.escolas.id, 'team_id': self.equipa.id}, **vals)
                )

    def test_exclusao_por_nif_telefone_e_listas_de_bloqueio(self):
        Exclusao = self.env['kututa.prospect.exclusion']
        Exclusao.create({'organizacao': 'X', 'nif': '5000 999 888'})
        self.assertEqual(self._entrada(nif='5000999888').estado, 'excluido')
        Exclusao.create({'organizacao': 'Y', 'phone_sanitized': '00244 912 345 678'})
        self.assertEqual(self._entrada(telefone='912345678', email=False, place_id=False).estado, 'excluido')
        self.env['mail.blacklist']._add('info@bloqueado.ao')
        self.assertEqual(
            self._entrada(organizacao='Outro', email='info@bloqueado.ao', telefone=False, place_id=False).estado,
            'excluido',
        )

    def test_rejeitar_com_exclusao(self):
        lead = self._entrada().lead_id
        assistente = (
            self.env['kututa.prospect.rejeitar']
            .with_user(self.vendedor)
            .create({'lead_ids': [Command.set(lead.ids)], 'motivo': 'Pediu para não ser contactado', 'excluir': True})
        )
        assistente.action_rejeitar()
        self.assertEqual(lead.kp_verificacao, 'rejeitado')
        self.assertFalse(lead.active)
        self.assertTrue(lead.kp_reter_ate)
        self.assertTrue(lead.kp_excluido)
        self.assertEqual(self._entrada(place_id=False).estado, 'excluido')

    # ------------------------------------------------------------------ o n8n não sai do contrato
    def test_n8n_nao_toca_em_leads_exclusoes_nem_mensagens(self):
        lead = self._entrada().lead_id
        Lead = self.env['crm.lead'].with_user(self.n8n)
        with self.assertRaises(AccessError):
            Lead.search([])
        with self.assertRaises(AccessError):
            Lead.create({'name': 'Lead do n8n'})
        with self.assertRaises(AccessError):
            lead.with_user(self.n8n).write({'name': 'x'})
        with self.assertRaises(AccessError):
            lead.with_user(self.n8n).unlink()
        with self.assertRaises(AccessError):
            self.env['kututa.prospect.exclusion'].with_user(self.n8n).search([])
        with self.assertRaises(AccessError):
            self.env['mail.mail'].with_user(self.n8n).create({'subject': 'x', 'email_to': 'a@b.ao'})
        with self.assertRaises(AccessError):
            self.escolas.with_user(self.n8n).write({'segmento': 'outro'})
        with self.assertRaises(AccessError):
            self.env['kututa.prospect.intake'].with_user(self.n8n).search([]).write({'estado': 'criado'})

    def test_n8n_so_ve_perfis_activos_e_as_suas_entradas(self):
        uni = self.env.ref('kututa_prospect.profile_universidade')
        uni.active = False
        perfis = self.env['kututa.prospect.profile'].with_user(self.n8n).with_context(active_test=False).search([])
        self.assertNotIn(uni, perfis)
        self.assertIn(self.escolas, perfis)
        consultas = self.env['kututa.prospect.query'].with_user(self.n8n).search([])
        self.assertFalse(consultas.filtered(lambda q: q.profile_id == uni))
        outro_tecnico = self.env['res.users'].create(
            {
                'name': 'Outro n8n',
                'login': 'n8n-2@kututa.ao',
                'group_ids': [Command.set([self.env.ref('kututa_prospect.group_prospect_integration').id])],
            }
        )
        alheia = (
            self.env['kututa.prospect.intake']
            .with_user(outro_tecnico)
            .create({'profile_code': 'escolas', 'fontes_json': '[]'})
        )
        self.assertNotIn(alheia, self.env['kututa.prospect.intake'].with_user(self.n8n).search([]))

    # ------------------------------------------------------------------ verificação e guardas
    def test_verificacao_so_pelos_botoes(self):
        lead = self._entrada().lead_id.with_user(self.vendedor)
        for contexto in ({}, {'kututa_prospect_trusted': True, 'su': True}):
            with self.subTest(contexto=contexto), self.assertRaises(AccessError):
                lead.with_context(**contexto).write({'kp_verificacao': 'verificado'})
        with self.assertRaises(AccessError):
            lead.write({'kp_justificacao': 'inventada'})
        with self.assertRaises(UserError):
            lead.write({'stage_id': self.env.ref('crm.stage_lead2').id})
        manual = (
            self.env['crm.lead']
            .with_user(self.vendedor)
            .create({'name': 'Manual', 'kp_profile_id': self.escolas.id, 'kp_verificacao': 'verificado'})
        )
        self.assertEqual(manual.kp_verificacao, 'nao_verificado')
        self.assertEqual(manual.stage_id, self.revisao)

    def test_aprovar_sai_de_para_rever_e_cria_cadencia(self):
        lead = self._entrada().lead_id
        lead.with_user(self.vendedor).action_kp_verificar()
        self.assertEqual(lead.kp_verificacao, 'verificado')
        self.assertEqual(lead.kp_verificado_por, self.vendedor)
        self.assertNotEqual(lead.stage_id, self.revisao)
        self.assertEqual(len(lead.activity_ids), len(self.escolas.cadencia_ids))
        self.assertIn('manual', lead.kp_fonte_ids.mapped('fonte'))

    def test_outra_equipa_nao_ve_nem_verifica(self):
        lead = self._entrada().lead_id
        self.assertNotIn(lead, self.env['crm.lead'].with_user(self.outro_vendedor).search([]))
        with self.assertRaises(AccessError):
            lead.with_user(self.outro_vendedor).read(['name'])
        with self.assertRaises(AccessError):
            lead.with_user(self.outro_vendedor).action_kp_verificar()
        normal = self.env['crm.lead'].create({'name': 'Lead do chat', 'team_id': self.equipa.id})
        self.assertIn(normal, self.env['crm.lead'].with_user(self.outro_vendedor).search([]))

    def test_vendedor_nao_muda_perfis_nem_apaga_exclusoes(self):
        with self.assertRaises(AccessError):
            self.escolas.with_user(self.vendedor).write({'segmento': 'x'})
        exclusao = self.env['kututa.prospect.exclusion'].with_user(self.vendedor).create({'nif': '123'})
        with self.assertRaises(AccessError):
            exclusao.unlink()

    # ------------------------------------------------------------------ IA
    def test_classificacao_valida_grava_pontuacoes(self):
        lead = self._entrada().lead_id
        cliente = ClienteFalso([resposta(classificacao())])
        with self._com(cliente):
            self.ia._cron_classificar()
        self.assertEqual(lead.kp_pontuacao, 80)
        self.assertEqual(lead.kp_produto_principal_id, self.escolas)
        self.assertEqual(lead.kp_produto_secundario_ids, self.env.ref('kututa_prospect.profile_empresas'))
        self.assertTrue(lead.kp_classificado_em)
        self.assertIn('Número de alunos', lead.kp_justificacao)
        pedido = cliente.pedidos[0]
        self.assertEqual(pedido['model'], 'claude-haiku-5-5')
        self.assertEqual(pedido['output_config']['format']['type'], 'json_schema')
        self.assertIn('<dados_da_organizacao>', pedido['messages'][0]['content'])
        self.assertEqual(self.env['kututa.ia.uso'].search_count([('kp_lead_id', '=', lead.id)]), 1)
        # Já classificado: o cron não volta a pedir.
        with self._com(ClienteFalso([])):
            self.ia._cron_classificar()

    def test_classificacao_invalida_nao_grava_nada(self):
        lead = self._entrada().lead_id
        casos = [
            resposta('{"produto_principal": "escolas"'),
            resposta(classificacao(pontuacao=150)),
            resposta(classificacao(), stop='max_tokens'),
            resposta(classificacao(), stop='refusal'),
            resposta(classificacao(etapa='Ganho', vendedor='admin')),
        ]
        for caso in casos:
            with self.subTest(stop=caso.stop_reason), self._com(ClienteFalso([caso])), mute_logger(ia_mod.__name__):
                self.ia._classificar(lead)
            self.assertFalse(lead.kp_classificado_em)
            self.assertFalse(lead.kp_score_ids)
        self.assertEqual(lead.stage_id, self.revisao)

    def test_classificacao_descarta_perfis_desconhecidos_e_limita_obrigatorio(self):
        lead = self._entrada().lead_id
        dados = classificacao(cumpridos=['Mais de 200 alunos'], produtos_secundarios=['escolas', 'inventado'])
        dados['pontuacoes'].append(
            {'perfil': 'inventado', 'pontuacao': 99, 'criterios_cumpridos': [], 'justificacao': 'x'}
        )
        with self._com(ClienteFalso([resposta(dados)])):
            self.ia._classificar(lead)
        self.assertEqual(lead.kp_pontuacao, 30)  # falhou o critério obrigatório
        self.assertEqual(set(lead.kp_score_ids.profile_id.mapped('code')), {'escolas', 'empresas'})
        self.assertFalse(lead.kp_produto_secundario_ids)  # o principal não entra nos secundários

    def test_rascunho_tem_frase_de_recusa_e_respeita_a_agt(self):
        lead = self._entrada().lead_id
        bom = {'assunto': 'Pautas sem Excel', 'corpo': 'Olá.\n\nFacturação: {{ kututa_agt }}'}
        with self._com(ClienteFalso([resposta(bom)])):
            lead.with_user(self.vendedor).action_kp_gerar_rascunho()
        self.assertIn(ia_mod.FRASE_RECUSA, lead.kp_rascunho)
        self.assertIn('{{ kututa_agt }}', lead.kp_rascunho)
        self.assertTrue(lead.activity_ids)
        mau = {'assunto': 'Software certificado pela AGT', 'corpo': 'Olá.'}
        with self._com(ClienteFalso([resposta(mau)])), self.assertRaises(UserError):
            lead.with_user(self.vendedor).action_kp_gerar_rascunho()
        with self.assertRaises(UserError):
            lead.with_user(self.vendedor).write({'kp_rascunho': '<p>O Kututa é certificado pela AGT.</p>'})
        self.env['ir.config_parameter'].sudo().set_str('kututa_prospect.agt_estado', 'certificado')
        lead.with_user(self.vendedor).write({'kp_rascunho': '<p>O Kututa é certificado pela AGT.</p>'})

    def test_texto_html_da_ia_e_escapado(self):
        lead = self._entrada().lead_id
        dados = {'assunto': '<script>x</script>', 'corpo': '<img src=x onerror=alert(1)>Olá'}
        with self._com(ClienteFalso([resposta(dados)])):
            lead.with_user(self.vendedor).action_kp_gerar_rascunho()
        self.assertNotIn('<script>', lead.kp_rascunho)
        self.assertNotIn('<img', lead.kp_rascunho)

    # ------------------------------------------------------------------ retenção e instalação
    def test_retencao_apaga_dados_so_do_google_ao_fim_de_30_dias(self):
        google = json.dumps(
            [{'campo': 'organização', 'url': 'https://maps.google.com/?cid=1', 'fonte': 'google_places'}]
        )
        so_google = self._entrada(fontes_json=google).lead_id
        misto = self._entrada(
            organizacao='Colégio B', telefone='923999888', email=False, place_id='ChIJ2', fontes_json=google
        ).lead_id
        misto.sudo().write(
            {'kp_fonte_ids': [Command.create({'campo': 'telefone', 'fonte': 'lista_med', 'url': 'https://med.ao'})]}
        )
        antigo = fields.Datetime.now() - timedelta(days=31)
        (so_google | misto).kp_fonte_ids.filtered(lambda f: f.fonte == 'google_places').write({'data_recolha': antigo})
        self.env['crm.lead']._kp_cron_retencao()
        self.assertFalse(so_google.active)
        self.assertFalse(so_google.phone)
        self.assertFalse(so_google.partner_name)
        self.assertEqual(so_google.kp_place_id, 'ChIJteste1')
        self.assertTrue(misto.active)
        self.assertEqual(misto.phone, '+244923999888')

    def test_instalacao_recusada_fora_da_vimeo(self):
        self.empresa.vat = '5000004251'
        with self.assertRaises(UserError):
            hooks.pre_init_hook(self.env(context=dict(self.env.context, kututa_prospect_testar_guarda=True)))
        self.empresa.vat = hooks.VIMEO_NIF
        hooks.pre_init_hook(self.env(context=dict(self.env.context, kututa_prospect_testar_guarda=True)))
