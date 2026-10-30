# Fase 8: `kututa_prospect` (prospecção comercial assistida por IA)

> **Aprovado a 30/10/2026, sem o envio de e-mail (fica para o fim).** Implementado em `custom_addons/kututa_prospect`:
> entregas 8a, 8b, 8c e 8d, mais o rascunho da mensagem e a retenção dos dados do Google (24 testes). Falta a 8e (modelos
> de e-mail, servidor de saída, envio só para verificados) e o resto da 8f (relatórios, parecer do jurista).
>
> **Decisões do dono do projecto e da implementação:**
> - **n8n:** na VPS actual **só para testes**, com limite de memória; no arranque real passa para uma VPS separada.
> - **Equipa:** os quatro perfis apontam para a equipa «Vendas» que já existe; a etapa «Para rever» é só dessa equipa.
> - **Tipo do registo:** os leads de prospecção nascem como oportunidades (`type = opportunity`) na etapa «Para rever»,
>   para aparecerem no pipeline mesmo com os «Leads» do CRM desligados. Nascem sem vendedor; quem verifica fica com eles.
> - **Modelo de IA:** Haiku 5.5 por omissão; a classificação nasce desligada (`kututa_prospect.ia_activa`).
> - **Frase de recusa**, neutra no género: «Se preferir não receber mais contactos nossos, diga-nos e retiramos os seus
>   dados.»
> - **Leads de entrada** (chat do site, formulário): a guarda de exclusão só se aplica a leads com perfil de prospecção.
> - **Custos da IA:** registados no mesmo modelo do chat (`kututa.ia.uso`, campo `kp_lead_id`), por isso o módulo
>   depende do `kututa_ai_chat`.
> - **Telefones:** normalizados pelo próprio módulo (E.164, +244), porque a biblioteca `phonenumbers` pode faltar.

## 1. Objectivo e âmbito

### Objectivo
Dar à equipa comercial da Kututa **um só motor de prospecção**, que encontra organizações candidatas, as classifica
e prepara o primeiro contacto. O produto entra como **configuração**: o motor não sabe nada sobre escolas nem
restaurantes. Lê o perfil de prospecção do produto e age conforme ele.

O módulo corre **só no Odoo interno da Kututa** (base `kututa`, empresa Vímeo, NIF 5003603490), que é o CRM de vendas
da própria empresa. **Nunca** corre nas bases dos clientes (`vovoeva`, `lbdf` e as futuras).

### Entra nesta fase
- **Perfis de prospecção**, um por produto: segmento, fontes e consultas, cargos, critérios, dores, proposta de valor,
  tom, canais, cadência, equipa e pipeline.
- **Extensão do `crm.lead`**: perfil de origem, produto principal e secundários, pontuação e justificação, fonte de
  cada dado, estado de verificação e chave de deduplicação.
- **Revisão humana obrigatória**: etapa «Para rever», sem envio a leads não verificados.
- **Lista de exclusão global**, respeitada por qualquer criação de lead e por qualquer envio.
- **Entrada de leads vindos do n8n**, por uma «caixa de entrada» própria (`kututa.prospect.intake`) e nunca por
  escrita directa no `crm.lead`.
- **Classificação por IA** (Claude), com resposta em JSON validada pelo Odoo antes de gravar.
- **Rascunho da mensagem** gerado pela IA e gravado no lead para revisão.
- **Modelos de e-mail por perfil** no `mass_mailing`, enviados por um servidor de saída dedicado.

### Fica de fora
| Tema | Motivo |
|---|---|
| WhatsApp dentro do Odoo | O módulo de WhatsApp só existe no Enterprise. O WhatsApp fica fora do Odoo: Cloud API da Meta via n8n, ou envio manual. O Odoo só regista a actividade. |
| Pesquisa e recolha dentro do Odoo | É feita pelo n8n, que fica com a chave do Google. O Odoo só recebe, valida e decide. |
| Envio automático sem pessoa | Fase futura, se a decidirem. Nesta fase cada envio sai de um clique humano sobre leads verificados. |
| Scraping de redes sociais ou da pesquisa do Google | Proibido pelos termos dessas plataformas e pela política de dados deste plano (§11). |
| Instalação nas bases dos clientes | O módulo recusa instalar-se fora da Vímeo (§1.1). |

### 1.1 Como se garante que só corre no Odoo interno
1. **Dependências do manifest** só fazem sentido no CRM interno: `crm`, `sales_team`, `mass_mailing_crm`,
   `phone_validation` e `sale_management` (para os produtos KUT-*). Não depende de nenhum `edu_*` nem de
   `l10n_ao_edi`: os perfis descrevem esses produtos, mas não precisam do código deles.
2. **Guarda na instalação**, como já faz o `tools/carregar_tabela_precos.py`: um `pre_init_hook` recusa a instalação
   (com `UserError`) se nenhuma empresa da base tiver o NIF 5003603490. Fica também uma verificação em tempo de
   execução: o cron de classificação e o processamento das entradas param, e registam um aviso, se a empresa do lead
   não for a Vímeo.
3. **Documentação de instalação** (README do módulo e `docs/comercial/`): instalar só com
   `-i kututa_prospect -d kututa`. As linhas de implantação em lote das bases dos clientes nunca o incluem.
4. **Teste automático** que prova a recusa da instalação numa empresa com outro NIF.

## 2. Modelos e campos

Convenções: versão `20.0.1.0.0`, licença `OPL-1`, autor `Kututa ERP`, `countries: ['ao']`, textos directamente em
português, sem `.po`. O nome no manifest segue o padrão «Marca - Função»: **«Kututa ERP - Prospecção»**.

### 2.1 `kututa.prospect.profile`: perfil de prospecção (um por produto)
| Campo | Tipo | Notas |
|---|---|---|
| `name` | Char, obrigatório | «Gestão escolar», «Universidade»… |
| `code` | Char, único | `escolas`, `universidade`, `restauracao`, `empresas`. É o que o n8n e a IA usam. |
| `active` | Boolean | Um perfil inactivo não aparece ao n8n nem à IA. |
| `sequence` | Integer | |
| `product_tmpl_ids` | Many2many `product.template` | Produtos de venda ligados (KUT-ESC-*, KUT-UNI-*…). Domínio: só os da empresa Vímeo. |
| `segmento` | Text | Descrição do segmento-alvo, em linguagem natural (vai para a IA). |
| `query_ids` | One2many `kututa.prospect.query` | Fontes e consultas por cidade ou província. |
| `cargos` | Text | Um cargo por linha («Director(a) geral», «Director(a) pedagógico(a)»…). |
| `criterio_ids` | One2many `kututa.prospect.criterion` | Critérios de qualificação, com peso. |
| `dores` | Text | Dores a abordar (uma por linha). |
| `proposta_valor` | Html | Proposta de valor, com funcionalidades reais. Usada no rascunho e nos modelos. |
| `tom` | Selection + Text | `institucional`, `proximo` ou `tecnico`, mais notas livres. |
| `canal_email` / `canal_telefone` / `canal_whatsapp` / `canal_visita` | Boolean | Canais permitidos. O WhatsApp é sempre externo ao Odoo. |
| `cadencia_ids` | One2many `kututa.prospect.cadence` | Passos de follow-up. |
| `team_id` | Many2one `crm.team`, obrigatório | Equipa de vendas destino. |
| `stage_review_id` | Many2one `crm.stage` | Por omissão, a etapa «Para rever» do módulo. |
| `mailing_template_ids` | Many2many `mailing.mailing` | Modelos de e-mail do perfil (campanhas em rascunho que servem de base). |
| `company_id` | Many2one `res.company` | Sempre a Vímeo. |

### 2.2 `kututa.prospect.query`: fonte e consulta
| Campo | Tipo | Notas |
|---|---|---|
| `profile_id` | Many2one, obrigatório, `ondelete='cascade'` | |
| `fonte` | Selection | `google_places`, `lista_med`, `lista_mescti`, `lista_publica` ou `manual`. Não há opção para redes sociais. |
| `consulta` | Char | Texto da pesquisa, por exemplo «colégio» ou «restaurante». |
| `provincia` | Selection | As 21 províncias (divisão de 2024). |
| `cidade` | Char | |
| `url_lista` | Char | Endereço da lista pública (MED, MESCTI), quando é uma lista. |
| `active` | Boolean | |
| `ultima_execucao` | Datetime, só de leitura | Escrita pelo processamento das entradas. |

### 2.3 `kututa.prospect.criterion`: critério de qualificação
`profile_id`, `name` (por exemplo «Tem mais de 300 alunos»), `peso` (Integer 1–5) e `obrigatorio` (Boolean). Vão
para a IA como lista. A pontuação é dada pela IA, mas um critério obrigatório falhado limita-a a 30 (validação no
Odoo, §6.3).

### 2.4 `kututa.prospect.cadence`: passo de follow-up
`profile_id`, `sequence`, `dias_apos` (Integer), `canal` (Selection: e-mail, telefone, WhatsApp externo, visita),
`activity_type_id` (Many2one `mail.activity.type`) e `nota` (Char). Depois da verificação do lead, a cadência cria
**actividades** para o vendedor. Não envia nada sozinha.

### 2.5 `kututa.prospect.exclusion`: lista de exclusão global
| Campo | Tipo | Notas |
|---|---|---|
| `nif` | Char, indexado | Normalizado: só dígitos e letras, em maiúsculas. |
| `email_normalized` | Char, indexado | Com `email_normalize`. |
| `phone_sanitized` | Char, indexado | Com o `phone_validation` (E.164, prefixo +244). |
| `chave_nome_cidade` | Char, indexado | A mesma função da chave de deduplicação (§2.7). |
| `organizacao` | Char | Para leitura humana. |
| `motivo` | Selection | `recusou`, `pediu_remocao`, `opt_out_email`, `outro`. |
| `profile_id` | Many2one | Produto que recusou. **Só informativo:** a exclusão vale para todos os produtos. |
| `origem_lead_id` | Many2one `crm.lead`, `ondelete='set null'` | |
| `data` | Datetime | |
| `user_id` | Many2one `res.users` | Quem registou. |

Um registo exclui se **qualquer** das chaves coincidir. Ao criar uma exclusão, o e-mail entra também na
`mail.blacklist` e o telefone na `phone.blacklist` do núcleo, para que o `mass_mailing` e o SMS também a respeitem.
O sentido inverso também funciona: um opt-out feito pelo link do `mass_mailing` cria a exclusão global.

### 2.6 `kututa.prospect.intake`: caixa de entrada do n8n
É o **único modelo onde o n8n escreve**. Funciona como uma área de trânsito com registo para auditoria.
| Campo | Tipo | Notas |
|---|---|---|
| `profile_code` | Char, obrigatório | Perfil que originou a pesquisa. |
| `query_id` | Many2one `kututa.prospect.query` | Opcional. |
| `organizacao`, `nif`, `email`, `telefone`, `website`, `morada`, `cidade`, `provincia` | Char | Só dados institucionais (§11). |
| `cargo_contacto`, `nome_contacto` | Char | Só quando aparecem numa fonte institucional pública (site da organização, lista oficial). |
| `place_id` | Char | Identificador do Google Places, o único dado do Google que pode ficar guardado sem prazo (§11.2). |
| `fontes_json` | Text | Lista `[{campo, url, fonte, data}]`. É obrigatória: uma entrada sem fonte é rejeitada. |
| `estado` | Selection | `pendente`, `criado`, `duplicado`, `excluido`, `rejeitado`, `erro`. |
| `lead_id` | Many2one `crm.lead` | Lead criado ou encontrado. |
| `mensagem` | Char | Motivo do estado, que o n8n pode ler. |
| `create_uid` | (padrão) | O utilizador técnico. |

O processamento corre **no `create`, em `sudo`, depois de validar os dados**: normaliza, verifica a exclusão,
deduplica e só então cria ou actualiza o lead. Detalhe no §7.

### 2.7 Extensão do `crm.lead`
| Campo | Tipo | Notas |
|---|---|---|
| `kp_profile_id` | Many2one `kututa.prospect.profile`, indexado | Perfil de origem. |
| `kp_produto_principal_id` | Many2one `kututa.prospect.profile` | Produto principal (o produto é o perfil). |
| `kp_produto_secundario_ids` | Many2many `kututa.prospect.profile` | Venda cruzada. |
| `kp_score_ids` | One2many `kututa.prospect.score` | Pontuação por produto: `profile_id`, `pontuacao` (0–100) e `justificacao`. |
| `kp_pontuacao` | Integer, stored, calculado | Pontuação do produto principal. Permite ordenar e filtrar. |
| `kp_justificacao` | Text | Justificação geral da IA. |
| `kp_classificado_em` | Datetime | |
| `kp_modelo_ia` | Char | Modelo que classificou, para auditoria. |
| `kp_fonte_ids` | One2many `kututa.prospect.source` | Fonte de cada dado: `campo`, `url`, `fonte`, `data_recolha`. |
| `kp_place_id` | Char, indexado | |
| `kp_nif` | Char, indexado | NIF normalizado. |
| `kp_verificacao` | Selection | `nao_verificado` (por omissão nos leads de prospecção), `verificado`, `rejeitado`. Com tracking. |
| `kp_verificado_por` / `kp_verificado_em` | Many2one `res.users` / Datetime | Só de leitura. |
| `kp_motivo_rejeicao` | Char | |
| `kp_dedup_key` | Char, stored, calculado, indexado | Por prioridade: `nif:<NIF>`, depois `tel:<phone_sanitized>`, depois `nc:<nome-normalizado>\|<cidade-normalizada>`. |
| `kp_rascunho` | Html | Rascunho da mensagem gerado pela IA. |
| `kp_excluido` | Boolean, calculado (não stored), pesquisável | Verdadeiro se alguma chave do lead estiver na exclusão. |
| `kp_reter_ate` | Date | Data de apagamento dos dados de contacto (§11.4). |

Os campos `kp_verificacao`, `kp_verificado_*`, `kp_score_ids`, `kp_pontuacao` e `kp_justificacao` só mudam pelos
métodos do módulo, nunca por escrita directa. Segue-se o padrão do `edu_fees`: a escrita directa dá `AccessError`, e
o contexto enviado pelo cliente não abre excepções (§4.4).

### 2.8 Afirmação sobre a AGT (um só sítio)
O Kututa **ainda não está homologado pela AGT**. A afirmação comercial vive num único sítio:
- dois parâmetros de sistema, só para o Gestor: `kututa_prospect.agt_estado` (`em_homologacao` ou `certificado`) e
  `kututa_prospect.agt_texto`. Por omissão: «Facturação electrónica preparada para o modelo da AGT (DP 71/25 e DE
  683/25), em processo de certificação.»;
- os modelos de e-mail e os rascunhos da IA usam o marcador `{{ kututa_agt }}`, substituído no envio;
- **validação no envio e no rascunho**: enquanto o estado não for `certificado`, qualquer texto que contenha
  «certificad» a menos de 40 caracteres de «AGT» é bloqueado com `UserError` (há teste para isto);
- quando a homologação sair, muda-se o estado e o texto (com o número da certificação) **e mais nada**.

## 3. Vistas e menus

Menu **CRM › Prospecção** (grupo Prospecção / Utilizador):
- **Leads para rever**: lista do `crm.lead` filtrada por `kp_verificacao = nao_verificado`, ordenada por
  `kp_pontuacao`. Colunas: organização, perfil, produto principal, pontuação, cidade, n.º de fontes e etapa.
- **Entradas do n8n** (`kututa.prospect.intake`), só de leitura: estado, motivo e lead.
- **Exclusões** (`kututa.prospect.exclusion`), com o botão «Adicionar exclusão».
- **Configuração › Perfis de prospecção** (só Gestor): formulário com separadores Produto, Pesquisa, Qualificação,
  Mensagem e Cadência.

No formulário do `crm.lead`, para leads com perfil:
- separador **«Prospecção»**: pontuações por produto, justificação, fontes (com links clicáveis), chave de
  deduplicação e rascunho;
- botões no cabeçalho: **«Aprovar (verificado)»**, **«Rejeitar»**, **«Classificar com IA»**, **«Gerar rascunho»** e
  **«Excluir de todas as campanhas»**;
- uma faixa vermelha quando `kp_excluido` é verdadeiro, e uma amarela quando o lead ainda não foi verificado
  («Não pode receber mensagens até ser verificado»).

Kanban do pipeline: a etapa **«Para rever»** aparece em primeiro lugar, só para a equipa de prospecção.

## 4. Segurança

### 4.1 Grupos
O privilégio `res_groups_privilege_prospect` («Prospecção») segue o padrão de `sales_team_security.xml` e
`edu_core/security/`:

| Grupo | Implica | Para quem |
|---|---|---|
| `group_prospect_user`: Prospecção / Utilizador | `sales_team.group_sale_salesman` | Vendedores que revêem e contactam leads. |
| `group_prospect_manager`: Prospecção / Gestor | `group_prospect_user` e `sales_team.group_sale_manager` | Quem configura os perfis e os parâmetros da AGT e apaga exclusões. |
| `group_prospect_integration`: Prospecção / Integração (n8n) | `base.group_user`, e mais nada | Só o utilizador técnico do n8n. |

### 4.2 Acessos (`security/ir.access.csv`)
| Modelo | Utilizador | Gestor | Integração (n8n) | Justificação |
|---|---|---|---|---|
| `kututa.prospect.profile` | `r` | `crud` | `r`, domínio `[('active','=',True)]` | Só o Gestor muda a estratégia comercial. O n8n só lê os perfis activos. |
| `kututa.prospect.query` | `r` | `crud` | `r`, domínio `[('active','=',True),('profile_id.active','=',True)]` | O n8n precisa das consultas para pesquisar. |
| `kututa.prospect.criterion` / `.cadence` | `r` | `crud` | — | O n8n não precisa delas. |
| `kututa.prospect.intake` | `r` | `r` | `cr`, domínio `[('create_uid','=',user.id)]` | O n8n cria entradas e lê o estado das suas. Ninguém escreve nem apaga, porque é o registo de auditoria. |
| `kututa.prospect.exclusion` | `cr` | `crud` | — | Qualquer vendedor pode excluir (proteger é sempre permitido). Só o Gestor apaga, e só depois do prazo de retenção (§11.4). O n8n não lê a lista: a verificação é feita no servidor. |
| `kututa.prospect.score` / `.source` | `r` | `r` | — | São escritos pelo servidor, em `sudo`, nos métodos do módulo. |
| `crm.lead` | (núcleo) | (núcleo) | — | **O n8n não tem nenhum acesso ao `crm.lead`.** |

Não há nenhum `d` (unlink) para o n8n nem para o utilizador em nenhum modelo, e nenhum acesso ao `mail.mail`,
`mailing.mailing` ou `mail.compose.message` para o n8n.

### 4.3 Regras por registo (coluna `domain` do `ir.access.csv`, que no Odoo 20 substitui a `ir.rule`)
1. **Os leads de prospecção ficam na equipa.** Uma linha de restrição (sem grupo, logo global) em `crm.lead`:
   `['|', '|', ('kp_profile_id', '=', False), ('team_id', 'in', user.crm_team_ids.ids), ('team_id.user_id', '=', user.id)]`.
   - *Porquê:* os dados de prospecção (fontes, pontuações, rascunhos) são da equipa que os trabalha. Hoje os
     vendedores com «todos os leads» vêem tudo.
   - *Âmbito:* não toca nos leads normais (`kp_profile_id` vazio), por exemplo os do chat do site.
   - *Gestores:* o líder de cada equipa passa pela terceira condição. O superutilizador e as operações em `sudo`
     (cron, n8n) não são afectados.
   - *A confirmar na implementação:* como as restrições se combinam com as permissões do `crm` (ler
     `ir_access.py:500-535`) e se o Gestor precisa de ser membro de todas as equipas de prospecção.
2. **Multi-empresa:** todos os modelos novos têm `company_id` e uma restrição `[('company_id','in',company_ids)]`,
   como o `crm_lead_company_rule` do núcleo.
3. **n8n:** o domínio `create_uid = user.id` nas entradas impede um utilizador técnico de ler as entradas de outro, se
   um dia houver mais do que um.

### 4.4 Regras nos métodos (o que o `ir.access` não consegue exprimir)
- `action_kp_verificar` / `action_kp_rejeitar`: exigem `group_prospect_user` e equipa do lead em
  `user.crm_team_ids`.
- `write` no `crm.lead`: recusa mudar os campos `kp_verificacao`, `kp_verificado_*`, `kp_score_ids`,
  `kp_pontuacao` e `kp_justificacao` fora desses métodos. Os métodos usam uma marca interna do servidor (não o
  contexto), como faz o `edu_fees`.
- `write` no `crm.lead`: recusa tirar o lead da etapa «Para rever» enquanto `kp_verificacao != 'verificado'`.
- `create` no `crm.lead`: um lead com `kp_profile_id` cujo NIF, e-mail, telefone ou nome+cidade estejam excluídos dá
  `UserError`, qualquer que seja a origem (formulário, importação, API ou n8n).

## 5. Dados iniciais: os quatro perfis

Os textos abaixo saem do código existente (funcionalidades reais). O tom por omissão é `institucional`. O marcador
`{{ kututa_agt }}` substitui qualquer afirmação sobre a AGT.

### 5.1 Gestão escolar (`escolas`)
- **Produtos:** KUT-ESC-A1..A4 (Académico), KUT-ESC-C1..C4 (Completo) e KUT-ESC-IMP1..IMP4.
- **Segmento:** colégios privados e comparticipados, do primário ao secundário, e escolas técnico-profissionais.
  Começa por Luanda, Benguela e Huíla.
- **Fontes:** lista pública de escolas licenciadas do MED, quando existir em formato aberto; Google Places
  («colégio», «escola privada», «instituto médio») por cidade.
- **Cargos:** Director(a) geral, Director(a) pedagógico(a), Chefe de secretaria, Responsável financeiro(a).
- **Critérios:**
  - privada ou comparticipada (obrigatório);
  - mais de 200 alunos (peso 4);
  - tem site ou e-mail institucional (peso 2);
  - ensino técnico (peso 3, por causa do Despacho 60/08).
- **Dores:** pautas feitas à mão em Excel, erros no cálculo das médias, propinas em atraso sem controlo, emissão
  lenta de declarações e certificados, facturação electrónica obrigatória a partir de 1/1/2027.
- **Proposta de valor:**
  - pautas calculadas pelo regime oficial (DE 424/25 no geral, Despacho 60/08 no técnico), conselho de turma e
    reapreciação;
  - matrículas com vagas e número de ordem, transferências e rematrícula;
  - horários com detecção de conflitos e sumários com limites legais de faltas;
  - declarações, certificados, diplomas, mini-pautas, pautas A3 e cartão de estudante;
  - propinas com uma factura por cobrança, multas, bolsas aprovadas por outra pessoa e bloqueio de devedores;
  - Área do Estudante e do Encarregado;
  - migração a partir de outro sistema;
  - no plano Completo, também contabilidade e salários dos professores, com os tempos lectivos.
- **Cadência:** e-mail (dia 0), telefone (dia 3), e-mail de seguimento (dia 10) e visita, se houver resposta.

### 5.2 Universidade (`universidade`)
- **Produtos:** KUT-UNI-1..4 e KUT-UNI-IMP1..IMP4.
- **Segmento:** instituições de ensino superior privadas e públicas.
- **Fontes:** lista oficial de instituições do MESCTI (lista pública); Google Places («universidade», «instituto
  superior»).
- **Cargos:** Reitor(a), Vice-reitor(a) para os assuntos académicos, Secretário(a)-geral, Director(a) dos serviços
  académicos, Director(a) financeiro(a).
- **Critérios:** instituição licenciada pelo MESCTI (obrigatório); mais de 1 500 estudantes (peso 4).
- **Dores:** inscrições por unidade curricular com precedências feitas à mão, controlo de créditos e prescrição,
  emolumentos por UC, emissão de certificados e diplomas.
- **Proposta de valor:**
  - licenciatura e mestrado em semestres;
  - UCs com créditos, horas e tipo;
  - inscrição com precedências, limite de créditos e prescrição conforme o regulamento académico;
  - frequência, dispensa e exames normal, de recurso, especial e de melhoria;
  - transição por UCs em atraso e média pesada pelos créditos;
  - TFC e dissertação (DP 193/18);
  - emolumentos automáticos por UC;
  - portal do estudante.
- **Cadência:** e-mail institucional (dia 0) e telefone para marcar reunião (dia 5). Ciclo longo: seguimento mensal.

### 5.3 Restauração e retalho com POS (`restauracao`)
- **Produtos:** KUT-ESS (Essencial, com 1 POS) e KUT-POS (caixa adicional). Não há produto específico de
  restauração.
- **Segmento:** restaurantes, cafés, pastelarias, lojas e farmácias com uma a cinco caixas.
- **Fontes:** Google Places («restaurante», «pastelaria», «loja») por cidade.
- **Cargos:** Proprietário(a), Gerente.
- **Critérios:** estabelecimento com morada fixa (obrigatório); tem telefone público (peso 3); avaliações recentes
  (peso 1, sinal de actividade).
- **Dores:** obrigação de facturação electrónica a partir de 1/1/2027, falhas de internet, stock sem controlo.
- **Proposta de valor:**
  - talão de venda comunicado à AGT;
  - factura/recibo e factura a crédito no mesmo ecrã;
  - nota de crédito com motivo;
  - talão com QR e «2.ª via»;
  - **continua a vender sem internet** e emite o documento ao sincronizar;
  - stock actualizado a cada venda.
- **Limite a dizer com clareza:** não há talões próprios de restaurante (consulta de mesa, pré-conta). Ver
  `docs/fases/fase-2c-l10n_ao_edi_pos.md`. A proposta de valor **não** os promete.
- **Cadência:** visita ou telefone primeiro (dia 0). E-mail só se houver endereço institucional.

### 5.4 Empresas e facturação AGT (`empresas`)
- **Produtos:** KUT-ESS, KUT-NEG, KUT-EMP e KUT-CORP, com as implementações e os extras.
- **Segmento:** PME contribuintes de IVA no regime geral ou simplificado, que ficam obrigadas a 1/1/2027.
- **Fontes:** Google Places por sector e cidade; listas públicas de associações empresariais, quando forem abertas.
- **Cargos:** Director(a) geral, Director(a) financeiro(a), Contabilista, Responsável administrativo(a).
- **Critérios:** empresa com NIF ou site institucional (peso 3); 5 a 200 trabalhadores (peso 4).
- **Dores:** prazo de 1/1/2027, Excel e software não preparado, salários com IRT e INSS feitos à mão, SAF-T.
- **Proposta de valor:**
  - plano de contas PGC e impostos com os códigos AGT;
  - facturação electrónica com séries, comunicação e contingência ({{ kututa_agt }});
  - recibos com retenções;
  - SAF-T (AO);
  - Balanço e Demonstração de Resultados em PDF e Excel;
  - amortizações (DP 207/15);
  - salários com IRT (Lei 14/25), INSS de 3% e 8%, subsídios, ficheiro bancário e mapas;
  - contratos segundo a LGT.
- **Cadência:** e-mail (dia 0), telefone (dia 4) e e-mail sobre o prazo de 2027 (dia 14).

## 6. Contrato com o n8n e classificação pela IA

### 6.1 Utilizador técnico
- **Utilizador:** «n8n Prospecção» (login `n8n-prospect@kututa.ao`), interno, só com o grupo
  `group_prospect_integration`.
- **Sessão:** não tem palavra-passe utilizável, porque se cria com uma aleatória que ninguém guarda, e não entra pela
  interface.
- **Autenticação:** **chave de API do Odoo** (`res.users.apikeys`), criada pelo administrador em Preferências ›
  Segurança da conta e guardada só nas credenciais do n8n. Nunca a palavra-passe de uma pessoa.
- **Revogação:** apagar a chave corta o acesso de imediato. Rodar uma vez por ano.

### 6.2 Métodos que o n8n chama (API JSON-2 do Odoo 20: `POST /json/2/<modelo>/<método>`, `Authorization: bearer <chave>`)
| Chamada | Para quê |
|---|---|
| `kututa.prospect.profile` / `search_read` (domínio vazio, campos `code`, `name`, `segmento`, `cargos`, `query_ids`) | Ler os perfis activos. O `ir.access` já esconde os inactivos. |
| `kututa.prospect.query` / `search_read` | Ler as consultas: fonte, consulta, província, cidade, URL da lista. |
| `kututa.prospect.intake` / `create` (lista de até 50 registos) | Entregar candidatos, com as fontes. |
| `kututa.prospect.intake` / `search_read` (`[('id','in',ids)]`, campos `estado`, `mensagem`, `lead_id`) | Saber o resultado: criado, duplicado, excluído ou rejeitado. |

**O n8n não pode:** ler, criar, alterar ou apagar `crm.lead`; ler a lista de exclusão; enviar e-mails ou mensagens
(sem acesso ao `mail.mail`, `mailing.mailing` ou `mail.compose.message`); mudar perfis; verificar leads; apagar o que
quer que seja. Também não pede a classificação à IA: ela corre no Odoo depois da criação do lead (§6.3). Há um teste
para cada uma destas proibições (§8).

**Limites:** no máximo 50 entradas por chamada e 2 000 por dia por utilizador técnico (parâmetro), para conter um n8n
avariado.

### 6.3 Classificação pela IA
- **Onde corre:** no Odoo, por cron (de 15 em 15 minutos, até 20 leads por volta) sobre os leads
  `nao_verificado` sem classificação, e no botão «Classificar com IA».
- **Ligação à API:** o mesmo padrão do `kututa_ai_chat`: SDK `anthropic`, chave na variável de ambiente
  `ANTHROPIC_API_KEY`, modelo escolhido nas definições (Haiku 5.5 por omissão) e registo de custos.
- **O que a IA recebe:** os dados do lead (só institucionais) e a lista dos perfis activos (`code`, segmento,
  critérios, dores).
- **O que a IA devolve:** JSON pelas saídas estruturadas da API
  (`output_config={"format": {"type": "json_schema", "schema": ...}}`).

Esquema exacto:
```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["produto_principal", "produtos_secundarios", "pontuacoes", "justificacao", "dados_em_falta"],
  "properties": {
    "produto_principal": {"type": ["string", "null"], "description": "code de um perfil activo, ou null se nenhum serve"},
    "produtos_secundarios": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    "pontuacoes": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["perfil", "pontuacao", "criterios_cumpridos", "justificacao"],
        "properties": {
          "perfil": {"type": "string"},
          "pontuacao": {"type": "integer", "minimum": 0, "maximum": 100},
          "criterios_cumpridos": {"type": "array", "items": {"type": "string"}},
          "justificacao": {"type": "string", "maxLength": 600}
        }
      }
    },
    "justificacao": {"type": "string", "maxLength": 1200},
    "dados_em_falta": {"type": "array", "items": {"type": "string"}}
  }
}
```

**Validação no Odoo antes de gravar (nunca se confia na resposta):**
1. Faz `json.loads` e valida contra o esquema (com `jsonschema`, se estiver na imagem, ou validação manual). Uma
   resposta inválida ou cortada (`stop_reason` `max_tokens` ou `refusal`) não grava nada e regista o erro.
2. Cada `perfil`, `produto_principal` e `produtos_secundarios` tem de ser o `code` de um perfil **activo**. Os
   códigos desconhecidos são descartados.
3. O produto principal não pode aparecer nos secundários. Também não pode haver perfis repetidos.
4. A pontuação de um perfil com um critério obrigatório não cumprido fica limitada a 30. O Odoo compara os
   `criterios_cumpridos` com os critérios obrigatórios.
5. Os textos são cortados aos limites e gravados como texto simples (escapados no Html), nunca como Html vindo da IA.
6. A IA **não muda** a etapa, o vendedor, a verificação nem os dados de contacto. Só escreve a pontuação, a
   justificação e os produtos sugeridos.
7. Os dados do lead vão para a IA como dados, numa secção delimitada, com a instrução de que o texto vindo de sites
   não é uma instrução. Isto protege contra injecção de instruções pelos sites recolhidos.

### 6.4 Rascunho da mensagem
- **Origem:** o botão «Gerar rascunho», com o perfil (proposta de valor, dores, tom), os dados do lead e o produto
  principal.
- **Onde fica:** em `kp_rascunho` e numa actividade «Rever rascunho» para o vendedor. **Não se envia.**
- **Conteúdo obrigatório:** o rascunho inclui sempre a frase de recusa (§11.3) e o marcador `{{ kututa_agt }}` em vez
  de qualquer afirmação sobre a AGT. Passa pela validação do §2.8.

## 7. Fluxo completo de um lead
1. **Descoberta (n8n):** lê os perfis e as consultas activos e pesquisa nas fontes autorizadas (Google Places API,
   listas MED/MESCTI). Do Google guarda só o `place_id`; os outros dados vão para o Odoo marcados com a fonte e a data
   (ver §11.2 sobre o prazo).
2. **Entrega:** `create` em `kututa.prospect.intake`, com `fontes_json`.
3. **Validação:** o perfil tem de existir e estar activo; tem de haver pelo menos uma fonte com URL; os e-mails têm de
   ser institucionais (rejeita domínios de correio pessoal como gmail.com ou hotmail.com quando o nome é de uma
   pessoa, uma regra a afinar). Se falhar, `estado = rejeitado`.
4. **Normalização:** NIF, e-mail (`email_normalize`), telefone (E.164, +244), nome e cidade (minúsculas, sem
   acentos, sem «Lda»/«SA»/«Colégio»). Calcula a chave de deduplicação.
5. **Exclusão:** se qualquer chave estiver em `kututa.prospect.exclusion`, na `mail.blacklist` ou na
   `phone.blacklist`, fica `estado = excluido` e **não se cria nada**. O n8n só fica a saber que foi excluído, não
   porquê.
6. **Deduplicação:** procura um lead activo, ou perdido há menos de 12 meses, com a mesma `kp_dedup_key`, o mesmo
   `kp_place_id`, o mesmo `kp_nif`, o mesmo `phone_sanitized` ou o mesmo `email_normalized`.
   - **Se encontrar:** junta as fontes novas e os campos vazios, sem sobrescrever o que uma pessoa já verificou.
     `estado = duplicado`.
   - **Se encontrar um lead ganho ou um cliente existente:** não cria nada e avisa o vendedor (oportunidade de venda
     cruzada).
7. **Criação:** `crm.lead` com `type = lead`, equipa e etapa «Para rever» do perfil, `kp_verificacao =
   nao_verificado`, fontes em `kp_fonte_ids`, `source_id` UTM «Prospecção n8n» e o perfil como `kp_profile_id`.
   `estado = criado`.
8. **Classificação (cron da IA):** produto principal, secundários, pontuações e justificação, validados (§6.3).
9. **Revisão humana:** o vendedor abre «Leads para rever», confirma cada dado na fonte (com os links) e corrige-o.
   - **Aprovar:** `verificado`, sai de «Para rever» e cria as actividades da cadência.
   - **Rejeitar:** `rejeitado`, com motivo, perde o lead e marca `kp_reter_ate` (§11.4).
   - **Excluir:** cria a exclusão global e rejeita o lead.
10. **Rascunho:** gerado e revisto, editado à mão se for preciso.
11. **Envio** (sempre por uma pessoa):
    - **E-mail individual:** o compositor do lead recusa enviar se o lead não estiver `verificado` ou estiver
      excluído.
    - **Campanha `mass_mailing`:** os destinatários são filtrados no servidor por `crm.lead._mailing_get_opt_out_list`
      (o gancho existe em `mailing.py:965`), que devolve como opt-out os e-mails dos leads de prospecção não
      verificados, os excluídos e os da lista global. O domínio da campanha recebe também
      `[('kp_verificacao','=','verificado'), ('kp_excluido','=',False)]`, uma segunda barreira.
    - **WhatsApp e telefone:** fora do Odoo. O vendedor regista a actividade feita.
12. **Recusa:** o link de recusa do e-mail, ou um pedido por telefone ou WhatsApp registado pelo vendedor, cria a
    exclusão global. Daí em diante, nenhum perfil volta a criar ou contactar esse lead.

## 8. Plano de testes
Segue o estilo do projecto: `TransactionCase`, `@tagged('post_install', '-at_install', 'prospect')`, dados e
comentários em português, a API da Anthropic simulada (como em `kututa_ai_chat/tests`) e `make test m=kututa_prospect`.

**Funcionais**
- Criação de uma entrada: normaliza os dados, cria o lead em «Para rever» com as fontes e devolve `criado`.
- Deduplicação pelas cinco chaves: NIF, telefone, e-mail, `place_id` e nome+cidade. Uma entrada duplicada junta as
  fontes e não sobrescreve um campo verificado.
- Classificação: uma resposta válida grava as pontuações. Uma resposta com perfil desconhecido, pontuação 150,
  JSON inválido, `refusal` ou `max_tokens` não grava nada. O limite de 30 aplica-se a um critério obrigatório falhado.
- O rascunho contém a frase de recusa e o marcador da AGT.
- Aprovar cria as actividades da cadência.
- A recusa pelo link do `mass_mailing` cria a exclusão global, e vice-versa.

**Tentativas de violar as regras (todas têm de falhar)**
- O n8n (`with_user`) tenta `crm.lead.search`, `create`, `write` e `unlink`: `AccessError`.
- O n8n tenta ler `kututa.prospect.exclusion`, criar `mail.mail` ou `mailing.mailing`, ou chamar `action_send_mail`:
  `AccessError`.
- O n8n tenta ler um perfil inactivo, escrever num perfil, ou ler as entradas de outro utilizador técnico: vazio ou
  `AccessError`.
- O n8n entrega uma entrada sem fontes, ou com um perfil inactivo: `rejeitado`.
- Uma entrada com NIF, e-mail, telefone ou nome+cidade excluídos: `excluido`, sem lead.
- Um vendedor tenta criar à mão (formulário ou importação) um lead de prospecção excluído: `UserError`.
- Escrita directa de `kp_verificacao = 'verificado'`, também com `with_context(...)` forjado: `AccessError`.
- Mover um lead não verificado para fora de «Para rever»: `UserError`.
- Enviar um e-mail pelo compositor a um lead não verificado ou excluído: `UserError`.
- Uma campanha a uma lista com leads verificados, não verificados e excluídos: só os verificados e não excluídos
  recebem (`mailing.trace`).
- Um vendedor de outra equipa tenta ler um lead de prospecção: invisível na pesquisa e `AccessError` no `browse`.
- Um vendedor tenta mudar um perfil ou apagar uma exclusão: `AccessError`.
- Um modelo ou rascunho com «certificado pela AGT» enquanto o estado é `em_homologacao`: `UserError`.
- A instalação numa empresa sem o NIF da Vímeo é recusada (`pre_init_hook`).
- Uma resposta da IA que tenta mudar a etapa ou o vendedor (campos a mais no JSON): ignorada, porque o esquema e a
  validação não os aceitam.

## 9. Faseamento
| Entrega | Conteúdo | Gate |
|---|---|---|
| **8a** | Perfis (com os 4 iniciais, sem IA), campos no lead, etapa «Para rever», verificação (aprovar, rejeitar), guardas de escrita e de etapa, grupos, acessos e restrição por equipa. Criação manual de leads de prospecção. **Sem IA, sem n8n e sem envio.** | Testes de segurança verdes; um vendedor revê leads criados à mão na base `kututa`. |
| **8b** | Lista de exclusão global, normalização, chave de deduplicação, sincronização com a `mail.blacklist` e a `phone.blacklist`, e guarda no `create`. | Testes de exclusão e deduplicação verdes. |
| **8c** | Caixa de entrada `kututa.prospect.intake`, utilizador técnico, chave de API e contrato do n8n. Um fluxo n8n de teste com uma lista pública pequena. | O n8n cria leads e não consegue fazer nada fora do contrato (testes e prova manual). |
| **8d** | Classificação pela IA, com o esquema JSON e a validação. Registo de custos. | Uma amostra de 30 leads classificada e revista por uma pessoa; custo medido. |
| **8e** | Rascunhos, modelos de e-mail por perfil, afirmação AGT centralizada, servidor de saída dedicado, frase de recusa, envio só para verificados. | Campanha de teste para endereços internos: SPF, DKIM e DMARC a passar; os não verificados ficam de fora. |
| **8f** | Retenção (cron de anonimização), relatórios (fonte → lead → ganho) e ajustes. | Parecer do jurista aplicado. |

## 10. Entregabilidade (8e)
- **Subdomínio próprio** para a prospecção, por exemplo `contacto.kututa.ao`, com remetente
  `comercial@contacto.kututa.ao`. O e-mail operacional (`kututa.ao`, facturas e notificações do Odoo) fica separado,
  para que uma reputação estragada pela prospecção não afecte as facturas dos clientes.
- **Odoo:** um `ir.mail_server` dedicado («Prospecção»), com um SMTP de um fornecedor transaccional (por decidir) ou
  com a caixa da Angoweb para o subdomínio. Os `mailing.mailing` dos perfis usam `mail_server_id` = esse servidor.
  Nota: a base `kututa` **ainda não tem nenhum servidor de saída configurado**.
- **DNS** no gestor da Angoweb:
  - SPF do subdomínio só com o fornecedor escolhido (`v=spf1 include:<fornecedor> -all`);
  - DKIM com a chave do fornecedor;
  - DMARC a começar em `p=none` com relatórios, a passar a `quarantine` depois de 4 semanas limpas;
  - registo MX ou caixa de resposta, para as respostas e as recusas chegarem a alguém.
- **Volume:** aquecimento gradual (por exemplo, 20 e-mails por dia na primeira semana) e limite diário no parâmetro do
  módulo.
- **Conteúdo:** endereço físico da Vímeo, identificação da empresa e link de recusa em todas as mensagens.

## 11. Protecção de dados e termos de uso

### 11.1 Lei 22/11 (Protecção de Dados Pessoais), a validar por um jurista
- **Só contactos institucionais públicos:** e-mail e telefone gerais da organização e cargos publicados no site da
  própria organização ou numa lista oficial. Nada de contactos pessoais tirados de redes sociais. O nome de um
  director é um dado pessoal mesmo que esteja publicado: guarda-se só quando a fonte é institucional, e com a fonte.
- **Fonte de cada dado:** `kp_fonte_ids` (campo, URL, fonte e data), obrigatória à entrada.
- **Forma de recusar em todas as mensagens:** link de recusa no e-mail, e no telefone ou WhatsApp a frase «Se não
  quiser voltar a ser contactado(a), diga-nos e retiramos o seu contacto». Qualquer recusa entra na exclusão global.
- **Retenção (proposta):**
  - leads rejeitados: dados de contacto anonimizados ao fim de 6 meses (fica a organização, para estatística);
  - leads sem resposta depois da cadência completa: 12 meses;
  - exclusões: guardadas enquanto forem precisas para não voltar a contactar, só com as chaves (NIF, e-mail e
    telefone normalizados) e sem nomes de pessoas.

**Precisa de parecer do jurista:**
1. Se a prospecção B2B por e-mail a endereços institucionais precisa de consentimento prévio, ou se basta o interesse
   legítimo com direito de oposição.
2. Se o tratamento tem de ser notificado à Agência de Protecção de Dados (APD), ou autorizado por ela.
3. Se guardar nomes e cargos de dirigentes é aceitável, e com que informação ao titular.
4. Os prazos de retenção propostos.
5. O texto da frase de recusa e da informação sobre o tratamento.
6. A transferência de dados para fora de Angola: Anthropic (EUA), Google e o fornecedor de e-mail.

### 11.2 Termos das fontes
- **Só fontes com API oficial ou listas públicas:** Google Places API, listas do MED e do MESCTI, e listas públicas de
  associações. **Não há** scraping de Facebook, Instagram, LinkedIn nem da página de resultados do Google. O campo
  `fonte` nem tem essas opções.
- **Google Places, regras de cache (verificar a versão em vigor antes da 8c):**
  - os termos específicos do Google Maps Platform permitem guardar o **`place_id`** de acordo com as políticas do
    Places API;
  - latitude e longitude só podem ficar em cache **até 30 dias seguidos**;
  - para o resto do conteúdo (nome, morada, telefone, avaliações) os termos **não prevêem excepção de cache**.
  - **Consequência:** o dado do Google não pode ficar guardado sem prazo no CRM. Proposta:
    - o n8n entrega o `place_id` e os dados com a fonte `google_places` e a data de recolha;
    - na verificação, o vendedor confirma cada dado na fonte própria da organização (site, telefone atendido) e a
      fonte passa a ser essa;
    - um cron apaga, ao fim de 30 dias, os dados que ainda dependam só do Google e mantém o `place_id`.

    **A confirmar** com a leitura completa dos termos e das políticas do Places API em vigor.

### 11.3 Afirmações comerciais
- Nenhum modelo nem rascunho diz «certificado pela AGT» enquanto não houver homologação (§2.8, com validação e teste).
- **Fora deste módulo, mas encontrado na preparação:** o site kututa.ao (título da abertura e selo «Certificado pela
  AGT»), a base de conhecimento do chat (`custom_addons/kututa_ai_chat/data/conhecimento.md:12, 23, 38, 45`) e os
  resumos de vários manifests (`edu_fees`, `l10n_ao_edi`, `l10n_ao_edi_pos`) já falam em «certificado». O site e o
  chat são públicos, por isso convém corrigi-los já, independentemente deste módulo. Ver as perguntas em aberto.

### 11.4 Segredos
| Segredo | Onde vive | Porquê |
|---|---|---|
| Chave da API da Anthropic | Variável de ambiente `ANTHROPIC_API_KEY` no `.env` da VPS (a mesma do chat) | Fica fora da base de dados, logo fora das cópias de segurança (R2) e dos dumps, e não aparece a nenhum administrador do Odoo na interface. |
| Chave da Google Places API | Só nas credenciais do n8n, nunca no Odoo | Quem pesquisa é o n8n. Restringida na consola Google ao Places API e ao IP do n8n, com quota diária. |
| Chave de API do Odoo do utilizador técnico | Só nas credenciais do n8n | Revogável no Odoo sem mexer em mais nada. |
| SMTP do servidor de prospecção | `ir.mail_server` (o padrão do Odoo, só visível aos administradores) | O Odoo não lê SMTP de variáveis de ambiente sem código extra. É aceitável com o acesso restrito, mas fica registado como risco. |

Nenhum segredo vai para o código, para o git ou para `ir.config_parameter`.

## 12. Onde fica o n8n (pergunta do utilizador)
**A VPS actual** (Hetzner, 2 vCPU, 3,7 GiB de RAM, 75 GB de disco) tem hoje 965 MiB disponíveis e já usa 540 MiB de
swap. Medições de 30/10/2026:

| Processo | Memória |
|---|---|
| Odoo (4 workers) | 1,44 GiB |
| LabTIC (web, aovivo, postgres) | ~320 MiB |
| Postgres do Kututa | 170 MiB |
| Caddy | 19 MiB |

O CPU está quase parado (load 0,1) e o disco está a 34%.

O n8n em Docker precisa, segundo os guias de alojamento, de cerca de 2 GB para ser estável (a documentação oficial
não foi consultada). Em repouso usa algumas centenas de MiB, mas sobe com fluxos que mexem em muitos dados.

| Opção | Prós | Contras |
|---|---|---|
| A. n8n na mesma VPS, com `mem_limit` de 768 MiB, SQLite, atrás do Caddy em `n8n.kututa.ao` com acesso restrito | Custo zero | Pouca folga. Um pico do n8n empurra o Odoo de produção para a swap ou para o OOM killer. Junta no mesmo servidor as chaves do Google e o Odoo. |
| B. Aumentar a VPS para 8 GB (redimensionar na Hetzner) | Folga para o Odoo e o n8n | Reinício da VPS. Mantém tudo no mesmo servidor. |
| **C. VPS pequena separada só para o n8n** (recomendada) | Isola o risco: um n8n comprometido só tem a chave do utilizador técnico, que não chega ao `crm.lead`. Não mexe na produção. | Custo mensal extra e uma máquina a mais para manter (actualizações, cópias). |

**Recomendação:** a opção **C**. A opção A só serve como teste temporário, com limite de memória e com o Odoo a
reduzir para 3 workers. Confirmar os preços actuais na consola da Hetzner antes de decidir.

## 13. Riscos e perguntas em aberto

### Riscos
| Risco | Mitigação |
|---|---|
| Termos do Google Places impedem guardar os dados no CRM | Guardar só o `place_id`; apagar ao fim de 30 dias; verificação na fonte própria (§11.2). |
| Lei 22/11 exige consentimento ou notificação à APD | Parecer do jurista antes da 8e (envio). As entregas 8a–8d não contactam ninguém. |
| Reputação do domínio | Subdomínio e servidor dedicados, aquecimento, DMARC (§10). |
| Injecção de instruções pelos sites recolhidos | Dados tratados como dados no pedido à IA; a IA não tem ferramentas nem muda nada além da pontuação (§6.3). |
| Restrição por equipa mal combinada com as permissões do `crm` | Testes de leitura cruzada; confirmar `ir_access.py` na 8a. |
| Afirmações de certificação no site e no chat | Corrigir já, fora deste módulo (§11.3). |
| n8n na mesma VPS que a produção | Opção C (§12). |

### Perguntas para o dono do projecto
1. Aprova o nome e o faseamento 8a–8f, começando só por perfis, campos e revisão?
2. **Onde fica o n8n:** VPS separada (recomendado), aumento da VPS actual, ou na mesma VPS só para testes?
3. **Fornecedor de e-mail** de prospecção e nome do subdomínio (`contacto.kututa.ao`?).
4. **Jurista:** quem dá o parecer sobre a Lei 22/11, e até quando? (Bloqueia a 8e.)
5. **Leads de entrada** (chat do site, formulário): se alguém excluído voltar a contactar por iniciativa própria,
   cria-se o lead com um aviso (proposta) ou bloqueia-se? O pedido fala em «qualquer criação de lead», mas bloquear
   quem pede contacto parece contrário ao interesse dele.
6. **Afirmações «certificado»** no site kututa.ao, no chat com IA e nos manifests: corrijo-as já, numa tarefa
   separada?
7. **Restauração:** sem talões de restaurante, o perfil vende o Essencial com POS. Quer limitar o perfil a retalho
   até haver suporte de restaurante?
8. **Modelo de IA** da classificação: Haiku 5.5 (barato, por omissão) ou Sonnet 5.5?
9. **Equipa de prospecção:** uma equipa nova «Prospecção», ou os perfis apontam para a equipa «Vendas» que já existe?
10. Os prazos de retenção propostos (6 e 12 meses) servem como ponto de partida para o jurista?
