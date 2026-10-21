# Fase 5f: migração da Vovó Eva (`edu_migration_secped`)

**Estado:** concluída a 2026-10-21. A escola foi migrada da base local do secPed-Express (`secped_dev`) para uma base própria, `vovo_eva`: uma base por cliente, como em produção.

**Gate da Fase 5 cumprido:** a pauta do Odoo reproduz a do secPed **em todas as 19 554 disciplinas-aluno**.
- **19 395 iguais e 0 diferentes.** A classificação do ano no Odoo é igual à do secPed, com a CF assinada, a PG e a bonificação do conselho.
- **159 sem CF no secPed.** Também ficam incompletas no Odoo.

## Como correr
```bash
SECPED_DSN=postgresql://…@localhost:5432/secped_dev \
SECPED_SAIDA=/fora/do/repositorio \
SECPED_ENSAIO=1 \
    .venv/bin/python odoo/odoo-bin shell -c config/odoo.conf -d vovo_eva --no-http < tools/migrar_secped.py
```

Variáveis:
- `SECPED_ENSAIO=1`: corre tudo e desfaz no fim. Sem ela, cada fase é gravada ao terminar.
- `SECPED_FASES=grades,decisions`: corre só essas fases.
- `SECPED_ESCOLA`: o *slug* da escola no secPed (por omissão `vovo-eva`).
- `SECPED_LOGOTIPO`: ficheiro de imagem com o logótipo, que fica na ficha da escola.

Saída:
- Imprime as contagens e os indicadores.
- Grava `avisos.csv` e `pauta-diferente.csv` em `SECPED_SAIDA`. Estes ficheiros têm nomes de alunos e ficam **fora do repositório**.
- A base do secPed abre-se só para leitura.

**Duração na base local:** cerca de 20 minutos. A maior parte é o recálculo das 19 554 linhas da pauta.

## Desenho
- **Idempotência.** Cada registo importado fica em `ir.model.data`, no módulo `__secped__`, com o nome `<tabela>__<id do secPed>`. Correr de novo actualiza em vez de duplicar, e há um teste para isso.
  - O módulo `__secped__` não é um módulo instalado, por isso uma actualização do Odoo nunca apaga estes registos como «órfãos».
  - Os dados derivados (médias, notas, resultados) usam a chave natural: matrícula, disciplina e trimestre.
- **Contas de teste.** As contas com endereço `.test` (5 na Vovó Eva) e tudo o que lhes pertence ficam de fora.
- **Turmas.** Há uma turma do Odoo por oferta anual do secPed (`class_offerings`).
- **Matrículas.** O tipo (nova, rematrícula, repetente) e a ligação à matrícula anterior saem da sequência de anos de cada aluno.
- **Notas dos anos fechados.**
  - CT1 e CT2 entram como médias trimestrais importadas (`edu.term.result.imported`), que nunca se recalculam a partir das notas. A CF entra no 3.º trimestre e também como CF assinada (`imported_cf`).
  - A PG entra como avaliação «Prova global» do 3.º trimestre, com as notas.
  - As bonificações do conselho entram em `council_points`.
- **Regime.** O regime de avaliação da escola passa para o Odoo com os valores do secPed e com `technical_ca_precise`: a CF e a PG entram na CA sem arredondamentos intermédios, como no secPed.
- **Decisões.**
  - O Odoo calcula a decisão de cada aluno.
  - Quando o cálculo coincide com a pauta assinada, a decisão fica automática.
  - Quando não coincide, fica a decisão assinada, marcada como manual e com o fundamento «Decisão da pauta assinada».
  - As matrículas dos anos fechados passam a «Concluída» ou «Retido».
- **Reconciliação.** `_verify` compara as contagens e, nota a nota, a classificação final do Odoo com a fórmula do secPed (`secped_final`).

## Alterações noutros módulos
- **`edu_evaluation`:**
  - `edu.term.result.imported`, para a média da pauta assinada que não se recalcula.
  - Com `technical_ca_precise`, a PG também entra na CA sem arredondar, como no secPed. Antes era arredondada antes de combinar.
  - `imported_cf` com 4 casas decimais. Com 2 casas, uma CF como 12,8958 era gravada como 12,90.
  - Contexto `edu_defer_results`: a importação recalcula a pauta uma só vez, no fim.
- **`edu_timetable`:** contexto `edu_schedule_import`. O horário afixado entra com os choques de professor e de sala, que ficam no relatório para a escola corrigir. Os choques de turma continuam proibidos.

## O que migrou
| Dados | Origem (secPed) | Destino (Odoo) |
|---|---|---|
| Escola | `schools` | a empresa: nome, NIF, morada, tipo, natureza, directores, subtítulo do papel timbrado |
| Calendário | `academic_years`, `trimesters` | 4 anos e 12 trimestres, com os 9 dos anos fechados fechados e 2026/27 com o I Trimestre em curso |
| Instalações | `school_shifts`, `time_slots`, `rooms`, `departments` | turnos, tempos, salas, coordenações |
| Planos | `subjects`, `courses`, `curricula`, `curriculum_years`, `curriculum_subjects` | tal como estão no secPed, sem materializar o plano nacional |
| Turmas | `school_classes` × `class_offerings` | 82 turmas |
| Pessoas | `users` + `student_profiles`, `teacher_profiles` | 1 697 alunos com os números de matrícula (a sequência continua a seguir ao maior), 53 professores e a direcção |
| Contas | `users` (fase `users`) | 57 contas ligadas às fichas de funcionário: 53 professores, 2 da Direcção, a Secretaria e a Tesouraria (`financas@`), com os perfis da 5g. Login = email do secPed, sem palavra-passe: define-a quem administra |
| Matrículas | `enrollments`, `enrollment_subjects` | 3 194 matrículas com as disciplinas e o número de ordem |
| Docência | `subject_teachers`, `schedules` | atribuições (uma por ano quando o professor é o mesmo nos 3 trimestres) e o horário de 2026/27 |
| Notas | `grades`, `grade_council_adjustments` | 56 322 médias trimestrais, 19 395 CF assinadas, 18 612 PG, 238 bonificações |
| Decisões | `academic_records` | o resultado do ano de 1 633 alunos |
| Provas | `exam_periods`, `exam_sessions`, `exam_rooms`, `exam_supervisors` | a época do I Trimestre de 2026/27: as 24 sessões por turma do secPed dão 2 sessões com várias turmas |
| Propinas | `tuition_plans`, `tuition_fees`, `late_fee_configs` | 6 planos, 17 taxas (IVA 14% nas batas, uniformes e cartão; M21 no resto) e 5 multas |

## O que não migrou, e porquê
- **As 7 facturas de propinas do secPed.** Eram de teste. A facturação certificada (AGT) recomeça no Odoo.
- **Palavras-passe e contas sem perfil.** As palavras-passe do secPed não migram. A biblioteca, a reprografia, o RH e a contabilidade ficam sem conta até aos seus módulos. As contas dos alunos e encarregados vêm na Fase 6 (portal).
- **O logótipo.** A migração não o descarrega (está no armazenamento do secPed). Descarregou-se à parte e entrou com `SECPED_LOGOTIPO`.
- **Eventos do calendário, aulas e presenças, auditoria e permissões.** São 89 eventos, 2 aulas de teste e nenhuma presença. A auditoria e as permissões são técnicas do secPed; os perfis do Odoo são os da 5g.

## Achados (para a escola)
| Achado | Casos | O que fica no Odoo |
|---|---|---|
| A escola faz prova global em disciplinas que o Despacho 60/08 e a regra do plano não prevêem (2 tempos, componente técnica) | 50 linhas do plano | As linhas ficam marcadas com prova global, como a escola pratica. Sem isso, a PG lançada não entrava na CA (no secPed, uma PG lançada conta sempre) |
| Decisão assinada diferente do cálculo do regime | 270 de 1 633 (eram 331 antes das correcções às regras do técnico, `docs/analise-legal/05`) | A decisão assinada, como manual. Os casos mais frequentes são:<br>• «Transita» com 3 a 5 negativas (120): o cálculo dá recurso;<br>• «Transita» com uma disciplina sem classificação em dois trimestres (84): o regime dá «sem aproveitamento»; provavelmente são notas que faltam nas folhas entregues;<br>• «Não transita» com recurso possível (44) |
| Choques de professor no horário | 3 tempos (Osvaldo Soque à 6.ª às 07:00 e 07:50; Manuel Menezes à 5.ª às 13:50) | Ficam como estão |
| Epidemiologia Estatística na 12.ª de Análises Clínicas (A, B, C) sem estar no plano | 3 atribuições, 6 tempos | De fora, até a disciplina entrar no plano |
| Segunda grelha da tarde (a da 12.ª, que retoma às 15:40) | 3 tempos | As aulas ficam com as suas horas, sem tempo da grelha associado |
| Aluna pendente no secPed, transita com atraso no cálculo | 1 | A decisão calculada |

## Testes
São 7 testes no `edu_migration_secped`, sobre uma escola técnica em memória (`MemorySource`) com um ano fechado e um em curso:
- estrutura (escola, turmas, calendário, tempos sobrepostos, regime);
- pessoas e matrículas (aluno de teste excluído, tipo e ligação das matrículas, atribuição anual, aula fora do plano);
- notas (CT, CF de 4 casas, PG numa disciplina de 2 tempos, bonificação do conselho, reconciliação a zero);
- decisões (decisão assinada que vence o cálculo e estado da matrícula);
- provas e propinas;
- contas (perfil por papel, ligação à ficha de funcionário, contas de serviço sem perfil no relatório);
- idempotência (segunda passagem sem duplicar).

No `edu_evaluation` há mais um teste (`test_technical_imported`): médias importadas que não se recalculam e PG não arredondada na CA.

## Verificação no navegador
Pauta final da 12.ª A de Enfermagem (2025/26) gerada na base `vovo_eva`, com os nomes, as notas e as assinaturas da escola. Revelou um defeito do `edu_documents`: nas disciplinas classificadas só no fim do ano (Prática de Enfermagem), a pauta e o termo mostravam «00» nos CT. Corrigido: ficam vazios.

## Por fazer
- Rever com a escola as 270 decisões em que o regime e a pauta assinada divergem. A regra que a escola aplica de facto pode pedir afinar o regime técnico, por exemplo o número de negativas que admite a transição.
- Pôr a Epidemiologia Estatística no plano da 12.ª de AC, ou retirá-la do horário.
- Entregar à escola as palavras-passe temporárias das 57 contas (base local: ficheiro fora do repositório) e pedir que as mudem no primeiro acesso.
