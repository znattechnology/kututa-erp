# MuK (terceiros)

Peças da MuK IT (https://github.com/muk-it/odoo-modules, LGPL-3), copiadas sem alterações do ramo 20.0,
commit `51b6b20` (28/10/2026). Só as que convivem com o `kututa_web` (o menu lateral e o painel de mensagens
são nossos; o `muk_web_theme`, o `muk_web_appsbar` e o `muk_web_chatter` chocam com eles e ficam de fora):

| Módulo | Para quê |
|---|---|
| `muk_web_colors` | Cores da marca por base (Definições → Branding), modo claro e escuro |
| `muk_web_dialog` | Janelas: maximizar e tamanho por utilizador |
| `muk_web_refresh` | Botão de actualizar a vista (duplo clique: actualização automática) |
| `muk_web_list_column` | Largura das colunas das listas |
| `muk_web_list_mode` | Edição em linha nas listas |
| `muk_web_group` | Expandir e recolher todos os grupos |
| `muk_web_utils` | Base comum das anteriores |

A única coisa nossa é a tradução `i18n/pt.po` de cada módulo. Para actualizar: copiar de novo os módulos do
ramo 20.0, manter os `pt.po` e mudar aqui o commit.
