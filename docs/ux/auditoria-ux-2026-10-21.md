# Auditoria de UX: Kututa (Secretaria Express no Odoo) face ao secPed (2026-10-21)

**Método**
- **secPed:** percorrido no browser com as contas de demonstração da escola `isptec` (professor e serviços académicos), mais um inventário do código de `apps/web`.
- **Kututa:** percorrido na base `kututa_demo` como administrador, professor e tesouraria.
- **Capturas:** em `docs/ux/capturas/`.

**Veredicto**
- Os dados e as regras do Kututa já estão ao nível do secPed, e em vários pontos acima.
- A experiência ainda é a de um ERP genérico. O utilizador entra num chat. O trabalho diário está espalhado por registos soltos: uma avaliação de cada vez, uma linha por aluno e trimestre. Há também ruído do Odoo à vista: ícones partidos, tour preso, textos em inglês.
- O secPed é bom porque **organiza cada ecrã em torno da tarefa e de quem a faz**, não em torno do modelo de dados. É isso que temos de trazer.

## 1. O que o secPed faz bem e o Kututa deve herdar

| # | Princípio | Como aparece no secPed |
|---|---|---|
| 1 | **Cada perfil entra no seu painel**, escrito em frases | Professor: «Hoje», «As minhas turmas», «Novidades». Secretaria: «Por tratar» («Nada à espera. Todas as turmas têm director e horário…»), «As turmas», «Próximos 14 dias», «Atalhos». Finanças: «Estão em atraso X Kz, em N facturas, de M alunos» |
| 2 | **A pauta é o ecrã de trabalho do professor** | Disciplinas à esquerda; à direita, a grelha aluno × trimestre (MAC, NPT, MT, FJ, FI, MFD, CFD). Frase-resumo («1 positiva, 0 negativas, 1 sem nota final, média da turma 14,0»). Legenda das siglas. Trimestre corrente destacado. «Editar notas» abre as células e uma barra fixa «N alterações por guardar · Descartar · Guardar alterações» |
| 3 | **Cor das notas como no papel** | Positivas a azul (`#1F5FAE`), negativas a vermelho, **só na célula**. Notas inteiras («14», não «14,00») |
| 4 | **Chamada a partir do horário de hoje** | Um toque na aula de hoje abre a chamada. «Marcar todos presentes», contador «X de N presentes; 2 faltas», aviso «A chamada desta aula ainda não foi guardada.», alvos de 44 px no telemóvel |
| 5 | **O vazio e o erro dizem o que fazer** | «Hoje não tens aulas. No sábado, a primeira aula é Algoritmos… às 08:00.» Botões que dizem o que fazem: «Guardar a chamada», «Matricular na 10ª A», «Validar 3 comprovativos» |
| 6 | **Pagamento ao balcão legível** | «Propina de março de 2026», não o número da factura. Escolhe-se o que saldar; formas Numerário, TPA ou Depósito; dupla confirmação acima do limite |
| 7 | **Menu que se adapta à escola** | Estágios e PAP só no técnico, RDEC só com iniciação; barra inferior no telemóvel |

## 2. Achados no Kututa

### P0: defeitos visíveis (corrigir já, esforço pequeno): **feito a 2026-10-21**

| # | Achado | Prova | Correcção |
|---|---|---|---|
| A1 | **Ao entrar, o utilizador cai nas Discussões** (visto como administrador; nenhum perfil tem acção inicial definida), com a mensagem do OdooBot em inglês («Go ahead - Try sending me an emoji») | `kututa-entrada-discussoes.jpg` | Painel por perfil como acção inicial (ver B1). Até lá, `action_id` dos utilizadores para a primeira acção do seu menu |
| A2 | **20 ícones partidos em 15 ficheiros.** O Odoo 20 usa nomes Material Symbols (`group`, `check`, `menu_book`); os `icon="fa-users"`, `fa-book`, `fa-gavel`… aparecem como «-» ou com o glifo errado nos botões das fichas | `kututa-turma.jpg` (botões Alunos, Aulas, Faltas) | Trocar pelos nomes Material: `fa-users`→`group`, `fa-book`→`menu_book`, `fa-check`→`check`, `fa-money`→`payments`, `fa-lock`→`lock`, etc. Acrescentar um teste que falhe com `icon="fa-` |
| A3 | **Ponteiro de tour do Odoo preso** no canto superior esquerdo, por cima do título do menu lateral | todas as capturas do Kututa | Desactivar os tours por omissão (`web_tour`) nas bases de cliente |
| A4 | **Textos em inglês e em português do Brasil** vindos do núcleo: «12 records», «Unread», «Search Conversation», «Ativar notificações / Habilitar / Fique ligado!» | `kututa-mini-pauta.jpg`, `kututa-entrada-discussoes.jpg` | Ficheiro `i18n/pt_AO.po` no `kututa_web` com as traduções em falta, na norma de Angola/Portugal |
| A5 | **Menu duplicado na Direcção:** «Alunos» aparece em Alunos e em Propinas, porque a Direcção herda a Tesouraria | `kututa-ficha-aluno.jpg` (menu lateral) | Esconder `menu_edu_fee_students` a quem já tem a Secretaria |

### P1: fluxos de trabalho (onde está a diferença real)

| # | Achado | Prova | Proposta |
|---|---|---|---|
| B1 | **Não há painel por perfil.** A informação que o secPed põe em «Por tratar» existe no Kututa (candidaturas, devedores, turmas sem director, faltas em risco), mas obriga a abrir menus | — | Acção cliente Owl `edu_home`, uma por perfil, com secções em frases e ligações directas. Secretaria: por tratar, turmas, próximos dias, atalhos. Professor: hoje, as minhas turmas, avisos de faltas. Tesouraria: resumo da dívida, o que pede atenção, últimos pagamentos. Direcção: trimestres e alertas |
| B2 | **Notas lançadas uma avaliação de cada vez.** Para uma disciplina há 7 registos (contínua e prova por trimestre, prova global). O professor nunca vê a pauta inteira enquanto lança | `kututa-avaliacao.jpg` | **Widget «Pauta da disciplina»** (Owl), igual ao do secPed: disciplinas à esquerda; grelha aluno × trimestre com as colunas do regime (geral MAC/NPT/MT/MFD; técnico NPP/NPT/CT/CF/PG/CA); edição em lote com barra fixa; setas e Enter para navegar (o secPed não tem, é uma melhoria); grava nos `edu.grade` existentes e respeita a janela de lançamento |
| B3 | **A mini-pauta é uma lista agrupada.** Três níveis de grupos (turma, disciplina, trimestre); turma e disciplina repetidas em cada linha; médias de grupo sem significado; a linha inteira fica vermelha | `kututa-mini-pauta.jpg` | O mesmo widget da B2 em modo de leitura, com as legendas das siglas. A lista fica para a análise |
| B4 | **Notas com «,00» e só a vermelho.** As positivas não são azuis e a negativa pinta o aluno todo | `kututa-avaliacao.jpg`, `kututa-mini-pauta.jpg` | Widget de nota: inteiro quando a escala é inteira; azul `#1F5FAE` ou vermelho só na célula da nota |
| B5 | **Pagamento com nomes técnicos.** As facturas aparecem como «FT FT26DEMOSEDE/6» e a forma como «Caixa Kitanda»; não se escolhe o que saldar; o valor começa a 0 | `kututa-receber-pagamento.jpg` | Descrição legível («Propina de setembro de 2026», «Multa de atraso»); caixas para escolher as facturas; botão «Saldar tudo (56 000 Kz)»; formas Numerário, TPA e Depósito mapeadas para os diários; botão final com o valor («Receber 56 000 Kz») |
| B6 | **A chamada funciona, mas não parte de «hoje».** Abre-se em Aulas e sumários; faltam «Marcar todos presentes», o contador e o aviso de não guardada | `kututa-chamada.jpg` | «As minhas aulas» abre em «Hoje» (agrupado por hora). Na ficha da aula: botão «Todos presentes», contador no topo e botão final «Dar a aula» |
| B7 | **Títulos compridos e repetidos:** «Língua Portuguesa · 10ª A · ENF · 2026/2027 · 16/10/2026 · Lição 26» no título e nas migalhas | `kututa-chamada.jpg` | `display_name` mais curto conforme o contexto (na turma basta «LP · 16/10 · Lição 26»); o ano lectivo só quando não é o corrente |

### P2: identidade e consistência

| # | Achado | Proposta |
|---|---|---|
| C1 | O Kututa usa o roxo por omissão do Odoo (`#714B67`); o secPed tem identidade própria (areia, grafite, laranja de acção, Inter 400/500) | Tema no `kututa_web` com os tokens abaixo, para as variáveis SCSS do Odoo (`$o-brand-primary`, `$o-action`, fundos, bordas) |
| C2 | Tom de voz misturado (Odoo impessoal, alguns textos nossos com «tu») | Regra única: impessoal na administração e «tu» nos portais e no professor, como no secPed |
| C3 | Os estados vazios das acções `edu_*` são poucos e genéricos | Cada acção com um `help` que diga o próximo passo, como «Sem aulas por dar» |

## 3. Direcção visual proposta

A marca já existe: a identidade LabTIC do secPed, decidida pelo dono. A proposta adopta-a em vez de inventar outra. O que se muda são os valores por omissão do Odoo.

**Cor**

| Papel | Hex | Uso |
|---|---|---|
| Areia | `#FDF3EC` | Fundo das páginas e do painel |
| Linha | `#E5D9CE` | Bordas e separadores |
| Grafite | `#22252A` | Texto e barra de topo |
| Laranja de acção | `#C94E14` | Botão primário, item activo, foco |
| Azul das positivas | `#1F5FAE` | Só para notas positivas |
| Vermelho | `#C42B2B` | Negativas, erros, dívida vencida |

**Tipo:** Inter, só nos pesos 400 e 500, como no secPed. Escala: página 22, secção 18, corpo 14 (o Odoo é denso; 16 só nos portais), legenda 12.

**Composição:**
- Barra de topo grafite, fina.
- Menu lateral branco, com o item activo em areia e um traço laranja.
- Conteúdo sobre areia, com as fichas em branco.
- Os painéis vivem em duas colunas: tarefas à esquerda, contexto à direita.

```
┌──────────────── barra grafite ───────────────────────────────┐
│ menu  │  Painel · 2.º trimestre, até 31/03     [+ Matrícula] │
│ ───── │  Por tratar                       │ Próximos 14 dias │
│ ▌Hoje │  3 candidaturas por analisar   >  │ 22/10 Provas ... │
│ Turmas│  1 turma sem director          >  │ Atalhos          │
│ ...   │  As turmas (tabela)               │ ...              │
└──────────────────────────────────────────────────────────────┘
```

**Princípios**
1. O ecrã começa pela tarefa de hoje, não pelo modelo de dados.
2. As frases substituem os mosaicos de números.
3. A cor só tem significado quando é nota, dívida ou erro.
4. Cada botão diz o que acontece.

Nota: a combinação areia com laranja aproxima-se de um padrão muito comum em interfaces geradas. Aqui é a marca existente do cliente, por isso mantém-se. O que a distingue é o azul e o vermelho das pautas.

## 4. Plano proposto (antes da Fase 6)

| Passo | Conteúdo | Esforço |
|---|---|---|
| 1 | P0: ícones (A2), tour (A3), traduções `pt_AO` (A4), menu duplicado (A5), acção inicial provisória (A1). **Feito** | 0,5 dia |
| 2 | Tema `kututa_web` com os tokens (C1) e o widget de nota azul/vermelho (B4) | 1 dia |
| 3 | Widget «Pauta da disciplina» para lançar e consultar (B2, B3) | 2–3 dias |
| 4 | Painéis por perfil `edu_home` (B1) | 2 dias |
| 5 | Pagamento legível (B5), chamada a partir de hoje (B6), títulos curtos (B7), estados vazios (C3) | 1–2 dias |
| 6 | Verificação no telemóvel (professor e chamada) e revisão no browser por perfil | 0,5 dia |

## 5. O que ficou por verificar
- **Largura de telemóvel no Kututa:** não foi possível redimensionar a janela do browser. O menu lateral do `kututa_web` esconde-se em ecrãs pequenos (`ui.isSmall`), mas a chamada e a pauta não foram vistas no telemóvel.
- **Ecrãs do secPed vistos ao vivo:** só os do professor e da secretaria. Os de finanças e dos portais vêm do inventário do código.
- **PDF «cores e tipos de letra.pdf» na raiz do secPed:** é o guia de marca de outro projecto (VisaPower), não do secPed.

## 6. Passo 1 feito (2026-10-21)

| # | O que se fez |
|---|---|
| A1 | A Secretaria Express passou a ser a primeira aplicação do menu (sequência 1). Sem acção inicial, cada perfil entra na sua área, e não nas Discussões. O OdooBot deixou de enviar a conversa de boas-vindas em inglês. Os painéis por perfil (B1) vão substituir isto |
| A2 | Os 20 ícones `fa-*` passaram para nomes Material Symbols que existem no subconjunto do Odoo 20. O pre-commit rejeita `icon="fa-` e `class="fa ` |
| A3 | Os tours de boas-vindas do Odoo ficaram desligados para todos os utilizadores (`kututa_web`) |
| A4 | Há uma camada de traduções no `kututa_web` (`static/src/l10n/terms_pt_ao.js`) para os textos mais visíveis do núcleo (inglês ou português do Brasil), e «N registos» nos grupos das listas, que o Odoo 20 escreve em inglês fixo. **Falta:** o `pt.po` do núcleo tem mais de mil textos por traduzir só no `mail` e no `web`. Uma tradução completa para `pt_AO` é um trabalho à parte |
| A5 | A Tesouraria consulta os alunos no mesmo menu «Alunos» da Secretaria. Já não há duplicado para a Direcção |
| Novo | **Erro de acesso na ficha da turma** para quem não é do RH (Secretaria, professores). A grelha do horário lia campos de professor que não existiam no perfil público dos funcionários. Os campos passaram a existir em `hr.employee.public`. Há também um teste de fumo por perfil: abre a lista e a ficha de todos os menus visíveis |


## 7. Painéis por perfil: menu lateral da Secretaria (2026-10-21)
Primeiro painel revisto: o da Secretaria. O menu segue o do secPed para o perfil ADMIN_SERVICOS. A referência foi recolhida com a conta de demonstração do `isptec`.

**Menu lateral (`kututa_web`):**
- **Sem acordeão.** Todas as secções ficam abertas.
- **Títulos de secção:** em maiúsculas, na cor da marca, com fundo leve e um filete à esquerda.
- **Item activo:** com o mesmo filete.
- **Entradas soltas** (Disciplinas, Alunos): separam-se das secções.
- **Largura:** 240 px, para os títulos caberem inteiros.
- **Barra de topo:** com o menu lateral visível, deixa de repetir as secções. No telemóvel, onde não há menu lateral, continuam lá.

**Secções (`edu_roles/views/edu_secretaria_menu.xml`):**

| Secção | Itens |
|---|---|
| Configuração académica | Anos lectivos, Trimestres, Turnos lectivos, Tempos lectivos, Coordenações |
| Cursos e turmas | Cursos, Turmas, Salas, Currículo |
| Disciplinas | entrada solta |
| Docentes | Lista de docentes, Professores por disciplina, Directores de turma |
| Alunos | entrada solta; também a vê a Tesouraria |
| Matrículas | Candidaturas, Lista de matrículas, Nova matrícula, Cancelamentos, Transferências, Rematrícula |
| Cartão de estudante | Emissão de cartões |
| Horários | Por turma, Substituições, Aulas e sumários, Gerar aulas do horário, Justificação de faltas, Mapa de faltas |
| Exames | Calendário de provas, Sessões de exame, Exames extraordinários |
| Histórico académico | Mini-pauta, Autorizações de notas, Histórico do aluno, Diplomas e certificados, Declarações; depois Avaliações e notas, Pautas, Imprimir pautas, Conselhos de turma, Resultados do ano, Reapreciações, RDEC |
| Estágios | Lista de estágios, Novo estágio, Trabalho de fim de curso |
| Encarregados | Lista de encarregados, Criar encarregado, Vincular a aluno |

**Itens do Odoo sem equivalente no menu do secPed.** Ficam no fim da secção onde a Secretaria os procura:
- Tempos lectivos;
- Alunos e Rematrícula;
- a assiduidade, em Horários;
- o resto da avaliação, em Histórico académico.

**Permissões:** a Secretaria passa a criar e alterar a configuração académica, como no secPed (`academic:calendar:manage`, `classes:manage`, `subjects:manage`, `curriculum:update`): anos lectivos, trimestres, turnos, tempos, coordenações, cursos, disciplinas, salas e planos. Apagar continua só com a Direcção.

**Lista de docentes:** usa o perfil público dos funcionários. As fichas editam-se no RH.

**Sem equivalente no Odoo, por fazer:**
- Painel (passo 4 do plano);
- Calendário académico;
- Portaria — verificação do cartão;
- Editor visual de horários;
- Solicitações (todas, nova, tipos de documento), que é o `edu_secretaria` da Fase 6;
- Relatórios.

**Por fazer:** enquanto não houver painel, a Secretaria entra em «Anos lectivos», o primeiro item do menu.

## 8. Botão «Voltar» (2026-10-21)
Pedido do utilizador: quando se abre um registo ou outro ecrã a partir de uma lista, deve haver um botão para voltar onde se estava.

- **Onde está:** `kututa_web/static/src/back_button/`. No painel de controlo, antes do «Novo», aparece «← Voltar» sempre que se chegou ao ecrã a partir de outro: lista → ficha, ficha → alunos da turma, e assim por diante.
- **O que faz:** usa o trilho de navegação do Odoo. Volta ao ecrã anterior tal como estava, com os filtros, a página e o registo.
- **Onde não aparece:** no primeiro nível, por exemplo uma lista aberta pelo menu.
- **No telemóvel:** o Odoo já mostra uma seta de voltar, por isso o botão novo é só para o computador.
- **Atalho:** o trilho de navegação do Odoo (texto pequeno por cima do título) continua lá.
