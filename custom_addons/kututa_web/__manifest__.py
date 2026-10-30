{
    'name': 'Kututa ERP - Interface',
    'version': '20.0.1.5.0',
    'summary': 'Menu lateral recolhível, painel de mensagens escondido por omissão e layout dos documentos definido',
    'description': """
Kututa ERP: melhorias de navegação e de espaço no cliente web.

* Menu lateral à esquerda com as secções e os itens da aplicação aberta; recolhe-se com um botão e o
  estado fica guardado no navegador de cada utilizador
* O painel de mensagens e actividades dos formulários fica escondido por omissão; um botão no topo do
  formulário abre-o à direita, mais estreito (380 px), e a escolha fica guardada
* «Visualizar»: os relatórios abrem-se num separador com o PDF final, antes de imprimir
* Sem os tours de boas-vindas nem a conversa do OdooBot (em inglês)
* Correcções de tradução do núcleo para pt-AO nos textos mais visíveis
* Os documentos não mostram o logótipo de exemplo do Odoo quando a empresa ainda não tem logótipo
* O separador do navegador mostra o favicon do site da escola (ou o ícone do Kututa ERP), não o do Odoo
* Ecrãs de entrada e de redefinição da palavra-passe em português de Angola (o núcleo traz frases do Brasil)
* Cores da marca Kututa ERP na interface (em vez do roxo do Odoo) e app instalável (PWA) com o nome e os ícones Kututa
* Todas as empresas ficam com um layout de documentos definido, para a impressão sair logo em PDF em vez de
  abrir o assistente de configuração do Odoo
    """,
    'author': 'Kututa ERP',
    'category': 'Hidden/Tools',
    'depends': ['web', 'mail', 'mail_bot', 'web_tour'],
    'data': ['views/report_layouts.xml'],
    'assets': {
        'web._assets_primary_variables': [
            ('prepend', 'kututa_web/static/scss/marca.scss'),
        ],
        'web.assets_backend': [
            'kututa_web/static/src/**/*',
        ],
    },
    'post_init_hook': '_post_init_hook',
    'auto_install': True,
    'license': 'OPL-1',
}
