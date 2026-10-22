# Auditoria da fase 5 (académico): bugs e inconsistências

Data: 2026-10-22. Âmbito: os 36 commits de `9982674` a `5ada43a`, isto é, tudo o que mudou desde a auditoria de UX de
21/10. São cerca de 13 200 linhas em 180 ficheiros.

Foram cinco auditorias em paralelo, uma por área. Cada achado foi verificado assim:
- **C** (confirmado): reproduzido numa base própria, ou na `vovo_eva` com rollback;
- **P** (provável): só por leitura do código.

Nada foi gravado na `vovo_eva`. Os scripts dos ensaios estão no scratchpad da sessão (`audit5_*`).

Gravidade: **crít.** crítico, **alto**, **méd.** médio, **baixo**.

## Resumo

| Área | Crít. | Alto | Méd. | Baixo |
|---|---|---|---|---|
| Propinas, perfis e segurança | 1 | 3 | 3 | 3 |
| Avaliação e documentos | 2 | 5 | 5 | 4 |
| Matrículas | 0 | 6 | 8 | 4 |
| Horários, aulas, faltas e salários | 0 | 5 | 5 | 6 |
| Migração (código) | 0 | 2 | 3 | 2 |
| Migração (dados da Vovó Eva) | 0 | 2 | 4 | 3 |

Confirmado que está bem:
- **Gate da migração:** 19 395 classificações finais iguais às do secPed, 0 diferentes.
- **Dados actuais da Vovó Eva:**
  - os campos `current_*` dos alunos estão certos;
  - nenhum aluno tem duas matrículas abertas no mesmo ano;
  - as disciplinas inscritas estão todas no plano da turma.
- **Acessos dos perfis:**
  - o professor só vê as suas turmas;
  - os menus abrem para todos os perfis;
  - a tesouraria cobra e recebe.
- **Funcionamento:**
  - os crons de avisos não se repetem;
  - correr a confirmação de matrículas duas vezes não duplica nada.

## 1. Propinas, perfis e segurança

| # | Grav. | Achado | Verif. |
|---|---|---|---|
| 1.1 | crít. | A secretaria e a direcção não criam nem editam alunos e encarregados. `edu.student` e `edu.guardian` herdam de `res.partner`, e nenhum grupo `edu_*` implica `base.group_partner_manager`. Acontece com as contas reais da Vovó Eva. | C |
| 1.2 | alto | Mudar de turma ou de plano de propinas (ou criar um plano novo a meio do ano) volta a facturar os meses já facturados. A chave de idempotência usa o id da linha do plano. | C |
| 1.3 | alto | Quem se matricula a meio do ano nasce devedor. As taxas e a propina do mês vencem antes da data da matrícula, a multa é facturada logo e a matrícula fica «irregular». | C |
| 1.4 | alto | Mudar a categoria de uma linha do plano não muda o IVA nem o artigo: o cartão sai com M21 e o artigo «Propina», o que dá facturas AGT erradas. | C |
| 1.5 | méd. | Quatro olhos das bolsas: quem aprovou edita a bolsa e aprova a sua própria alteração (`requested_by_id` não é reposto). | C |
| 1.6 | méd. | A secretaria reabre um trimestre fechado com `write({'state': 'open'})`. Só o botão está protegido. | C |
| 1.7 | méd. | A taxa de candidatura nunca é cobrada: a categoria existe, mas nada a factura. | P |
| 1.8 | baixo | O cron desfaz a marcação manual «irregular». | C |
| 1.9 | baixo | Uma bolsa anulada impede criar outra do mesmo tipo no ano (UNIQUE inclui as anuladas). | C |
| 1.10 | baixo | `write` em várias bolsas devolve as anuladas a rascunho. | C |

## 2. Avaliação e documentos

| # | Grav. | Achado | Verif. |
|---|---|---|---|
| 2.1 | crít. | Classe de exame sem exame nacional lançado: a disciplina fica completa com a CF e o aluno conclui (DE 424/25, Anexo III). | C |
| 2.2 | crít. | A CFD faz a média de todos os resultados com o mesmo código de disciplina. Junta anos repetidos e outros níveis (por exemplo, LP da 9.ª com LP da 13.ª técnica). | C |
| 2.3 | alto | Técnico: disciplina com prova global sem PG lançada fica completa com CA = CF. Há 236 resultados importados assim. | C |
| 2.4 | alto | Exame numa disciplina plurianual técnica: o requisito, a pauta e a decisão contradizem-se, porque o exame devia substituir a CFD. | C |
| 2.5 | alto | `_after_exams` reescreve a decisão de um ano fechado (condicional → retido) e não volta a usar `grading.decide`. | C |
| 2.6 | alto | Reapreciação deferida depois do conselho não actualiza a decisão do ano. | C |
| 2.7 | alto | O assistente de confirmação ignora a decisão manual da direcção, porque lê o estado da matrícula. | C |
| 2.8 | méd. | A pauta não mostra a nota que decide (a CF sem bonificação nem exame). No técnico falta a CFD. | C |
| 2.9 | méd. | A pauta e a mini-pauta omitem as disciplinas do plano que ainda não têm notas. | C |
| 2.10 | méd. | A declaração com notas diz «Concluiu… Não apto» a quem está pendente ou em exame. | C |
| 2.11 | méd. | A marca «Exame nacional» da linha do plano é ignorada: usa-se a da disciplina, que é partilhada entre níveis. | P |
| 2.12 | méd. | Mudar o regime de avaliação não recalcula as médias trimestrais gravadas. | P |
| 2.13 | baixo | A mini-pauta técnica anuncia uma CT cumulativa e mostra a do trimestre. | C |
| 2.14 | baixo | Uma classe terminal configurada como condicional dá «Transita c/ atraso». | C |
| 2.15 | baixo | A listagem de transferências rebenta se uma transferência não tiver data. | P |
| 2.16 | baixo | As disciplinas na classe anterior são propostas fora do savepoint da confirmação: um erro aborta o lote todo. | P |

## 3. Matrículas

| # | Grav. | Achado | Verif. |
|---|---|---|---|
| 3.1 | alto | A seriação ignora os candidatos já aprovados e não limpa os resultados antigos: podem ficar mais admitidos do que vagas. | C |
| 3.2 | alto | Uma entrada por transferência não se conclui depois do período de matrícula, porque pede o motivo do atraso e não há onde o pôr. | C |
| 3.3 | alto | A janela de matrícula não está presa ao ano lectivo, e matricular antes de abrir passa sempre. Hoje, na Vovó Eva, uma matrícula nova passa sem motivo. | C |
| 3.4 | alto | «Preparar» na confirmação fecha o ano ainda em curso: os alunos passam a «antigos» e a lista «Matriculados este ano» fica vazia. | C |
| 3.5 | alto | Uma transferência interna aprovada ainda pode mudar o destino para uma turma de outro ano. | C |
| 3.6 | alto | «Tentar de novo» numa linha sem turma dá `ValueError: Invalid field '_no_class'`. | C |
| 3.7 | méd. | A secretaria contorna os prazos de anulação com «Pedida pela escola» ou recuando a data. | C |
| 3.8 | méd. | Não se reactiva uma matrícula nova depois do período de matrícula, e a interface não tem saída para isso. | C |
| 3.9 | méd. | O prazo de anulação no técnico (5.º dia útil do III trimestre) cai dentro da pausa pedagógica: ignora feriados e pausas. | C |
| 3.10 | méd. | A mudança de curso deixa as disciplinas «na classe anterior» do curso antigo. | C |
| 3.11 | méd. | Reactivar depois de uma saída para outra escola deixa a transferência «Concluída». | C |
| 3.12 | méd. | A situação do aluno sai da última matrícula criada, mesmo quando outra está activa. | C |
| 3.13 | méd. | Pode anular-se uma matrícula concluída, retida ou em rascunho. | C |
| 3.14 | méd. | A secretaria edita as fases do calendário, que definem os prazos. | P |
| 3.15 | baixo | A seriação mistura as transferências e as classes que não são de entrada. | C |
| 3.16 | baixo | = 2.16. | P |
| 3.17 | baixo | Apagar uma «disciplina na classe anterior» deixa a disciplina na matrícula. | P |
| 3.18 | baixo | `edu.enrollment.document.type` não tem `company_id`. | P |

## 4. Horários, aulas, faltas e salários

| # | Grav. | Achado | Verif. |
|---|---|---|---|
| 4.1 | alto | Um professor cria aulas em qualquer turma: basta pôr-se como professor da aula, a regra do «substituto». | C |
| 4.2 | alto | A criação e a eliminação das linhas de chamada não verificam quem gere a aula, nem o trimestre fechado. | C |
| 4.3 | alto | `action_open_roll_call` não verifica permissões (cria as linhas com sudo). | C |
| 4.4 | alto | Mover ou trocar o professor de um tempo deixa as aulas já geradas no dia e com o professor antigo, e gerar outra vez duplica-as. | C |
| 4.5 | alto | O director de turma não justifica as faltas dos seus alunos nas disciplinas feitas noutra turma, e o director da turma da aula sim. | C |
| 4.6 | méd. | O professor de um tempo de um só trimestre não é o da colocação desse trimestre. | C |
| 4.7 | méd. | Mudar a disciplina de um tempo mantém o professor antigo. | C |
| 4.8 | méd. | Substituições: `original_teacher_id` e `class_id` podem ficar diferentes do tempo. O recibo usa esse campo e há um caso pago a dobrar. | C |
| 4.9 | méd. | Os professores não têm o menu «Justificação de faltas»: `edu_roles` substitui os grupos do menu. | C |
| 4.10 | méd. | Os métodos `editor_*` de leitura não verificam o grupo nem a empresa. | C/P |
| 4.11 | baixo | Aceita-se uma substituição num feriado, um tempo novo sobre uma substituição, domingo e um trimestre de outro ano. | C |
| 4.12 | baixo | Arrastar um tempo de 90 minutos encolhe-o para a duração da linha de destino. | C |
| 4.13 | baixo | A grelha «Ano todo» e o horário impresso ignoram os tempos de um só trimestre. | P |
| 4.14 | baixo | O editor parte-se com tempos que começam à mesma hora e têm durações diferentes (`t-key`). | P |
| 4.15 | baixo | «Imprimir» no editor depende do `edu_documents`, que não é dependência. | P |
| 4.16 | baixo | `edu_weekly_load*` dão AccessError fora do RH (hoje só se lêem com sudo). | C |

## 5. Migração do secPed

### Código

| # | Grav. | Achado | Verif. |
|---|---|---|---|
| 5.1 | alto | A fase de decisões não segue a ordem dos anos. Recalcular hoje muda 71 decisões automáticas, 51 delas contra a pauta assinada. | C |
| 5.2 | alto | Voltar a correr a migração desfaz trabalho feito depois. Confirmado: o plano, o Projecto Tecnológico, as aulas e as colocações. Provável: as anulações, as transferências, as disciplinas anuladas, os trimestres fechados, as decisões manuais e as datas de nascimento. | C/P |
| 5.3 | méd. | Os mapeamentos de estados estão incompletos para outras escolas (por exemplo, EXPELLED fica «transita»). | P |
| 5.4 | méd. | A data de saída das transferências sem `droppedAt` fica com a data da carga: 8 casos a 02/10/2026. | C |
| 5.5 | méd. | `_decide` cria exames por realizar e nunca os apaga: há 716 nos anos fechados. | C |
| 5.6 | baixo | `closed_date` dos trimestres fechados tem a data da carga. | C |
| 5.7 | baixo | A fase de contas liga um utilizador que já existe pelo login, sem confirmar quem é. | P |

### Dados da Vovó Eva

| # | Grav. | Achado | Decisão |
|---|---|---|---|
| 5.8 | alto | 71 decisões automáticas desactualizadas (2024/25 e 2025/26). | Técnica: recalcular por ordem e voltar a aplicar as assinadas |
| 5.9 | alto | 13.ª de 2026/27: 455 dos 518 alunos inscritos no Projecto Tecnológico já o fizeram e passaram na 12.ª. Nenhuma das 14 turmas tem professor no Projecto Tecnológico nem no Estágio. | **Escola** |
| 5.10 | méd. | 12.ª de Análises Clínicas: o plano novo tem «Epidemiologia» (2 tempos), o secPed lecciona «Epidemiologia Estatística» (6 tempos, sem colocações importadas). | **Escola** |
| 5.11 | méd. | `has_global_exam` desactualizado em 676 resultados (a classificação final não muda). | Técnica: recalcular |
| 5.12 | méd. | 716 exames por realizar em anos fechados. | Técnica: fechar |
| 5.13 | méd. | 21 alunos retidos matriculados numa classe superior no ano seguinte (6 da 10.ª para a 12.ª). Vem do secPed. | **Escola** |
| 5.14 | baixo | As 8 datas de saída das transferências. | Técnica: fim do ano |
| 5.15 | baixo | 82 turmas sem director nem sala (o secPed também não tinha). | **Escola** |
| 5.16 | baixo | 24 tempos da segunda grelha da tarde fora do turno (já conhecido). | **Escola** |
