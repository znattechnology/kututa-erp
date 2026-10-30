{
    'name': 'Kututa ERP - Chat do site com IA',
    'version': '20.0.1.1.0',
    'summary': 'O chat do site atende com IA (Claude): responde, qualifica, regista no CRM, marca demonstrações e '
    'prepara orçamentos em rascunho',
    'description': """
Só para a Vímeo (dona da marca Kututa), na base do site kututa.ao; não se instala nas bases dos clientes.

* Passo de bot «Conversa com IA»: cada mensagem do visitante é respondida pelo Claude, com a base de conhecimento
  do Kututa em cache e ferramentas validadas no servidor
* Ferramentas: registar contacto (crm.lead), consultar preços (produtos KUT-* da Vímeo), propor orçamento
  (sale.order em rascunho com actividade de aprovação), marcar demonstração (por confirmar) e passar para humano
* Registo de cada pedido à API (tokens e custo) e limite de respostas por conversa
* A chave da API vem da variável de ambiente ANTHROPIC_API_KEY (nunca da base de dados nem do git)
    """,
    'category': 'Website/Live Chat',
    'author': 'Kututa ERP',
    'depends': ['website_livechat', 'crm_livechat', 'sale_management', 'calendar'],
    'external_dependencies': {'python': ['anthropic']},
    'data': [
        'security/ir.access.csv',
        'data/chatbot.xml',
        'data/ir_config_parameter.xml',
        'views/res_config_settings_views.xml',
        'views/kututa_ia_uso_views.xml',
    ],
    'assets': {
        'im_livechat.assets_embed_core': ['kututa_ai_chat/static/src/common/**/*'],
        'mail.assets_public': ['kututa_ai_chat/static/src/common/**/*'],
        'portal.assets_chatter_helpers': ['kututa_ai_chat/static/src/common/**/*'],
        'web.assets_frontend': ['kututa_ai_chat/static/src/common/**/*'],
        'web.assets_backend': ['kututa_ai_chat/static/src/common/**/*'],
    },
    'license': 'OPL-1',
}
