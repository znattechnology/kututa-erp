{
    'name': 'Kututa ERP - Interface',
    'version': '20.0.1.1.0',
    'summary': 'Menu lateral recolhível, painel de mensagens escondido por omissão e layout dos documentos definido',
    'description': """
Kututa ERP: melhorias de navegação e de espaço no cliente web.

* Menu lateral à esquerda com as secções e os itens da aplicação aberta; recolhe-se com um botão e o
  estado fica guardado no navegador de cada utilizador
* O painel de mensagens e actividades dos formulários fica escondido por omissão; um botão no topo do
  formulário abre-o à direita, mais estreito (380 px), e a escolha fica guardada
* «Visualizar»: os relatórios abrem-se num separador com o PDF final, antes de imprimir
* Os documentos não mostram o logótipo de exemplo do Odoo quando a empresa ainda não tem logótipo
* Todas as empresas ficam com um layout de documentos definido, para a impressão sair logo em PDF em vez de
  abrir o assistente de configuração do Odoo
    """,
    'author': 'Kututa ERP',
    'category': 'Hidden/Tools',
    'depends': ['web', 'mail'],
    'data': ['views/report_layouts.xml'],
    'assets': {
        'web.assets_backend': [
            'kututa_web/static/src/**/*',
        ],
    },
    'post_init_hook': '_post_init_hook',
    'auto_install': True,
    'license': 'OPL-1',
}
