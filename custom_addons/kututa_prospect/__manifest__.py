{
    'name': 'Kututa ERP - Prospecção',
    'version': '20.0.1.0.0',
    'summary': 'Prospecção comercial assistida por IA: perfis por produto, caixa de entrada do n8n, exclusão global, '
    'classificação pelo Claude e revisão humana obrigatória',
    'description': """
Só para a Vímeo (dona da marca Kututa), no CRM interno da base kututa; recusa instalar-se noutra empresa.

* Perfis de prospecção, um por produto (escolas, universidade, restauração, empresas): segmento, fontes, cargos,
  critérios, dores, proposta de valor, tom, canais e cadência
* Leads de prospecção entram na etapa «Para rever» e só saem dela depois de verificados por uma pessoa
* Lista de exclusão global (NIF, e-mail, telefone, nome e cidade), sincronizada com as listas de bloqueio do Odoo
* Caixa de entrada para o n8n: o único modelo onde o n8n escreve; normaliza, exclui, deduplica e cria o lead
* Classificação pelo Claude com resposta em JSON validada antes de gravar, e rascunho da primeira mensagem
* A afirmação sobre a AGT vive num só sítio e é bloqueada enquanto o Kututa não estiver homologado
    """,
    'category': 'Sales/CRM',
    'author': 'Kututa ERP',
    'depends': ['crm', 'phone_validation', 'kututa_ai_chat'],
    'external_dependencies': {'python': ['anthropic']},
    'data': [
        'security/kututa_prospect_security.xml',
        'security/ir.access.csv',
        'data/crm_data.xml',
        'data/ir_config_parameter.xml',
        'data/ir_cron.xml',
        'data/kututa_prospect_profile_data.xml',
        'wizard/kututa_prospect_rejeitar_views.xml',
        'views/kututa_prospect_profile_views.xml',
        'views/kututa_prospect_intake_views.xml',
        'views/kututa_prospect_exclusion_views.xml',
        'views/crm_lead_views.xml',
        'views/res_config_settings_views.xml',
        'views/kututa_prospect_menus.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'countries': ['ao'],
    'license': 'OPL-1',
}
