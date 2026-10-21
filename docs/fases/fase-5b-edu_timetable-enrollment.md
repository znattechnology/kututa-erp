# Fase 5b: Secretaria Express, horários e matrículas (`edu_timetable`, `edu_enrollment`)

**Estado:** concluída a 2026-10-21. Testes: 5 no `edu_timetable` e 5 no `edu_enrollment`. A bateria dos 13 módulos tem 216 testes e 0 falhas. Instalado na base `kututa_demo`: a 10ª A de Enfermagem tem 3 alunos matriculados, colocações, director de turma e 13 tempos de horário.

**Fontes:** as regras dos serviços do secPed-Express, levantadas a partir do código:
- `enrollment.service.ts`, `enrollment-order.helper.ts` e `enrollment-subjects.helper.ts`;
- `application.service.ts` e `transfer.service.ts`;
- `schedule.service.ts`, `teacher.service.ts` e `shift.service.ts`.

## `edu_timetable`
| Modelo | Regras |
|---|---|
| `edu.time.slot` | Tempos por turno, dentro das horas do turno e sem sobreposições; grelha de 45 minutos com intervalo gerada num clique |
| `edu.teaching.assignment` (colocação) | Disciplina do plano da turma. **Um só professor por turma e disciplina em períodos que se cruzam**: a colocação do ano cruza-se com qualquer trimestre, e a do trimestre prevalece na data. Avisa quando o professor não está habilitado. O educador da iniciação não lecciona noutras turmas |
| `edu.class` | Director de turma: no máximo uma turma por professor e ano lectivo. Grelha semanal (tempos × dias). Aviso quando os tempos do horário diferem da carga do plano |
| `edu.schedule` | Professor por omissão a partir da colocação e sala por omissão a partir da turma. **Conflitos de turma, professor e sala** no mesmo dia e hora, com trimestres que se cruzam (o horário do ano cruza-se com tudo). Disciplina do plano da turma |
| `edu.schedule.exception` | Aula que não se realiza numa data (feriado, greve), sempre num dia do horário |
| `edu.schedule.replacement` | Substituto numa data: a aula tem de existir nessa data, o substituto não pode ser o próprio professor e tem de estar livre |
| `hr.employee` | Carga semanal com aviso: máximo 24 tempos, menos 4 para o coordenador de curso e menos 2 para o director de turma (regra do secPed) |

`_occurs_on` e `_teacher_on` dão as aulas efectivas de cada data. São a base dos sumários (5c) e da carga lectiva paga (`l10n_ao_payroll`).

## `edu_enrollment`
| Modelo | Regras |
|---|---|
| `edu.enrollment` | Estados: Pendente, Activa, Irregular (com propinas em atraso), Transferido, Anulada, Concluída, Retido; só Activa e Irregular ocupam vaga. **Vagas** verificadas na confirmação e na reactivação. **Uma matrícula por aluno e ano**. Na primeira matrícula, o aluno recebe o número de matrícula. **Número de ordem**: o seguinte na turma, fixo no ano, com quem entra a meio a ficar no fim. Disciplinas preenchidas pelo plano da turma e limitadas às da classe e das classes anteriores (atrasos). A anulação exige motivo (MED). Só uma matrícula pendente se elimina |
| `edu.class` | Alunos e vagas livres; «Numerar por ordem alfabética» no início do ano (os anulados e transferidos ficam no fim) |
| `edu.application` | Rascunho → Submetida → Em análise → Aprovada, Rejeitada (com fundamentação) ou Cancelada. A aprovação cria o aluno (ou reutiliza-o pelo BI) e o encarregado (reutilizado pelo telefone), e matricula o aluno na turma escolhida. Uma candidatura decidida não se altera |
| `edu.transfer` | Pendente → Aprovada → Concluída. Dentro da escola, a mesma matrícula muda de turma (as notas acompanham-na) e recebe o número de ordem seguinte. Numa mudança de curso ou de classe, as disciplinas são substituídas pelas do novo plano, mantendo as que já têm notas. A saída para outra escola fecha a matrícula como Transferido |
| `edu.enrollment.renewal` | Rematrícula de uma turma para um ano posterior: Rematrícula ou Repetente conforme a classe, sem duplicar quem já está matriculado |

### Pontos de extensão para as próximas sub-fases
- `edu.enrollment._edu_check_enrollment_allowed()`: retenções (máximo 2 por ciclo, fora do primário), resultado do ano anterior, disciplinas em atraso (5c).
- `edu.enrollment._edu_enrollment_warnings()`: propinas em atraso (5e).
- `edu.enrollment._edu_locked_subjects()`: disciplinas com notas, que não se retiram (5c).
- `edu.class._edu_can_renumber()`: os números de ordem deixam de mudar depois das primeiras notas (5c).

## Diferenças face ao secPed
| Tema | secPed | Kututa |
|---|---|---|
| Estado da matrícula | Sem máquina de estados; criada logo activa | Pendente → Activa, com acções explícitas (irregular, anular, reactivar) |
| Candidatura «em análise» | Nunca é usada | Acção «Pôr em análise» |
| Verificações na aprovação da candidatura | Sem retenção, sem ano anterior, sem dívidas | Passa pela confirmação da matrícula: todos os pontos de extensão se aplicam |
| Disciplinas na mudança de curso | Não são actualizadas | Substituídas pelas do novo plano, mantendo as que têm notas |
| Renumeração | Não existe (ficam buracos) | «Numerar por ordem alfabética», bloqueada depois das notas |
| Tempos, excepções e substituições | Sem serviço (só no esquema) | Modelos com validação |
| Horário face ao plano | Não verificado | Aviso por disciplina |
