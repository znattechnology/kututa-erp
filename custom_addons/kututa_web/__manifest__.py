{
    'name': 'Kututa ERP - Interface',
    'version': '20.0.1.0.0',
    'summary': 'Menu lateral recolhível e painel de mensagens escondido por omissão, em todas as aplicações',
    'description': """
Kututa ERP: melhorias de navegação e de espaço no cliente web.

* Menu lateral à esquerda com as secções e os itens da aplicação aberta; recolhe-se com um botão e o
  estado fica guardado no navegador de cada utilizador
* O painel de mensagens e actividades dos formulários fica escondido por omissão; um botão no topo do
  formulário abre-o à direita, mais estreito (380 px), e a escolha fica guardada
    """,
    'author': 'Kututa ERP',
    'category': 'Hidden/Tools',
    'depends': ['web', 'mail'],
    'assets': {
        'web.assets_backend': [
            'kututa_web/static/src/**/*',
        ],
    },
    'auto_install': True,
    'license': 'OPL-1',
}
