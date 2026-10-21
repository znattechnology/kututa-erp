# Fase 5a: Secretaria Express, núcleo académico e pessoas (`edu_core`, `edu_people`)

**Estado:** concluída a 2026-10-21. Testes: 7 no `edu_core` e 5 no `edu_people`. A bateria dos 11 módulos tem 206 testes e 0 falhas. Instalado na base `kututa_demo`, com uma escola de exemplo.

**Fontes:**
- `secPed-Express/apps/api/prisma/schema.prisma`: modelos School, AcademicYear, Trimester, Department, Course, SchoolClass, ClassOffering, Subject, Curriculum*, CurriculumTemplate*, Campus, Building, Room, SchoolShift, StudentProfile, Guardian, StudentGuardian e TeacherProfile;
- `prisma/templates/*.ts` e `curriculum-materializer.service.ts`: moldes curriculares nacionais e a sua composição.

## Plano da Fase 5
| Sub-fase | Módulos | Conteúdo |
|---|---|---|
| **5a** (esta) | `edu_core`, `edu_people` | Escola, anos lectivos, trimestres, cursos, disciplinas, planos curriculares, turmas, instalações; alunos, encarregados, professores |
| 5b | `edu_enrollment`, `edu_timetable` | Candidaturas, matrículas, número de ordem, transferências; grelha, horários, colocação de professores, director de turma |
| 5c | `edu_attendance`, `edu_evaluation` | Sumários e presenças; avaliações, motores do ensino geral (Dec. 424/25) e técnico (Despacho 60/08), conselho de turma |
| 5d | `edu_exam`, `edu_records`, `edu_documents` | Exames, histórico, certificados, pautas e restantes documentos oficiais |
| 5e | `edu_fees` | Propinas como facturas certificadas (`l10n_ao_edi`), bolsas, multas, bloqueio de devedores |
| 5f | `edu_migration_secped` | Migração da Vovó Eva e reconciliação das 19 554 notas |

## `edu_core`
| Modelo | Conteúdo |
|---|---|
| `res.company` (escola) | Subsistema, natureza, modo de cobrança (sem propina, mensal, comparticipada), níveis de ensino, código MED, n.º de registo, alvará, subtítulo do cabeçalho, lema, director geral e pedagógico, capacidade |
| `edu.level` | Seis níveis (iniciação, primário, secundário I e II ciclos, técnico-profissional, magistério) com o intervalo de classes |
| `edu.academic.year` / `edu.trimester` | Um ano em curso por escola, sem sobreposições; três trimestres gerados num clique; fecho do trimestre (Dec. 424/25, arts. 35.º a 38.º), que só a direcção reabre |
| `edu.course`, `edu.coordination`, `edu.subject` | Curso com nível e molde nacional (perfil); disciplinas com código nacional único por escola, componente de formação, duração plurianual e precedências sem ciclos |
| `edu.curriculum.template` (+ anos e linhas) | Catálogo nacional global: os 21 moldes do secPed (tronco comum de cada nível e perfis dos cursos), gerados por `tools/gen_edu_curricula.py` |
| `edu.curriculum` (+ anos e linhas) | Plano da escola. Ao criar o curso, é materializado o **tronco comum ⊕ perfil** (o perfil sobrepõe a carga e o exame), com as disciplinas da escola reutilizadas pelo código, como no secPed. Também há o plano do tronco comum de um nível sem curso |
| `edu.class` | Turma **por ano lectivo** («10ª A · ENF · 2026/2027»), com o plano e o ano do plano (classe e disciplinas), vagas, sala e turno; a classe tem de pertencer ao nível; uma sala fixa não serve duas turmas no mesmo turno |
| `edu.campus`, `edu.building`, `edu.room`, `edu.shift` | Instalações e turnos |

As 21 províncias (Lei n.º 14/24) foram acrescentadas ao `l10n_ao` (20.0.1.4.0), porque o Odoo não as traz.

## `edu_people`
| Modelo | Conteúdo |
|---|---|
| `edu.student` | Sobre `res.partner` (`_inherits`). O **número de matrícula** é vitalício: «ano da 1.ª matrícula-sequência», único na escola, e a sequência é global e nunca reinicia (sequência `no_gap` por escola). Não se altera nem se elimina depois de atribuído. Também guarda os dados dos documentos oficiais: BI, emissor e data, naturalidade e província, filiação, nacionalidade, necessidades especiais |
| `edu.guardian` | Sobre `res.partner`, com NIF (adquirente das facturas, DP 71/25, art. 10.º), BI e profissão |
| `edu.student.guardian` | Parentesco, encarregado principal (um por aluno; o primeiro associado é o principal), emergência, recolha, portal e avisos |
| `hr.employee` | Professor: especialidade, coordenação e disciplinas que pode leccionar |

## Decisões face ao secPed
| Tema | secPed | Kututa | Porquê |
|---|---|---|---|
| Turma | `SchoolClass` persistente mais `ClassOffering` por ano | Turma por ano lectivo | Mais simples de usar e de filtrar. A migração cria uma turma por oferta |
| Escola | Modelo `School` próprio | `res.company` | A escola é a entidade que factura (NIF, séries AGT, contabilidade) |
| Aluno e encarregado | `User` mais perfis | `res.partner` com `_inherits` | O encarregado é cliente nas facturas; o portal usa os utilizadores portal do Odoo |
| Números de matrícula importados | — | Contexto `edu_matricula_import` e `_sync_matricula_sequence` | A migração preserva os números e a sequência continua a seguir ao maior |
| Materialização na migração | — | Contexto `edu_no_materialize` | Os planos vêm do secPed tal como estão |

## Segurança
- Grupos «Secretaria» (alunos, encarregados e turmas; lê a configuração) e «Direcção» (configuração e reabertura de trimestres), na categoria Secretaria Express.
- Os dados pessoais dos alunos só são visíveis para a Secretaria. Os professores terão acesso às suas turmas na 5b/5c.
- Regras multi-empresa em todos os modelos com escola.

## Por fazer ou confirmar
- As cargas horárias dos moldes são as do secPed (ponto de partida). É preciso confirmá-las com as grelhas oficiais (Decreto Presidencial 162/23).
- Os códigos das províncias novas (Cuando, Cubango, Icolo e Bengo, Moxico Leste) não são ISO.
