# Fase 5c: Secretaria Express, sumários, presenças e avaliação (`edu_attendance`, `edu_evaluation`, `edu_payroll`)

**Estado:** concluída a 2026-10-21. A bateria dos 17 módulos tem 237 testes e 0 falhas. Instalado na base `kututa_demo`: a 10ª A de Enfermagem tem 88 aulas com chamada (Setembro e Outubro) e a pauta de Língua Portuguesa do ano inteiro, com prova global e um caso limite.

**Fontes:**
- Decreto Executivo n.º 424/25 (RAA), Anexo III e arts. 16.º, 21.º, 25.º, 31.º e 35.º–38.º;
- Despacho n.º 60/08 (técnico), arts. 4.º, 7.º, 13.º–21.º;
- resumo do regime de avaliação 2026/2027;
- regras do secPed-Express levantadas do código, com as divergências corrigidas: `docs/referencias/academico/secped-avaliacao-presencas.md`.

## `edu_attendance`: sumários e presenças
- **Aula** (`edu.lesson`): gerada a partir do horário, saltando as aulas sem realização, ou aberta pelo professor.
  - Leva professor efectivo (o substituto, quando o há), sala, horas, sumário e número de lição.
  - O trimestre é **deduzido da data** (o secPed deixava-o em branco).
  - Uma aula por tempo do horário e data; a data tem de bater com o dia do horário e estar dentro do ano lectivo.
  - Uma aula com chamada não se apaga: marca-se como não realizada.
- **Chamada** (`edu.lesson.attendance`): presente, atraso (conta como presença), falta injustificada, falta justificada.
  - A justificação regista o motivo, quem justificou e quando.
  - Só os alunos matriculados (activos ou irregulares) na disciplina entram na chamada.
- **Limites:**
  - ensino geral: 3, 4 ou 5 faltas injustificadas por trimestre e disciplina, conforme 1, 2 ou mais tempos semanais (RAA, art. 25.º);
  - técnico: o triplo dos tempos semanais no ano, e exceder numa disciplina exclui de todas (Despacho 60/08, art. 7.º);
  - os tempos semanais vêm do plano curricular;
  - «em risco» a uma falta do limite; «reprovado» ao atingir o limite.
- **Mapa de faltas** (`edu.absence.summary`): por aluno, disciplina e trimestre, só com aulas dadas.
- **Aviso ao director de turma:** uma actividade por disciplina, trimestre e situação. O secPed só avisava o aluno e o encarregado.
- **Permissões do professor:** gere as aulas das disciplinas em que está colocado, as da turma que dirige e as que substitui.

## `edu_evaluation`: avaliação
- **Regime por escola e nível** (`edu.evaluation.policy`), criado com os valores legais e editável:
  - escala e nota de aprovação;
  - arredondamento às unidades, metade para cima;
  - pesos e classes de exame;
  - transição condicional, com as negativas que não podem coincidir;
  - negativas que admitem recurso;
  - transição automática;
  - frequência mínima no primário (2/3);
  - retenções permitidas;
  - fórmula da classificação do curso.
- **Avaliações e notas:**
  - tipos: contínua, prova trimestral, prova global, exame nacional;
  - normalização da cotação para a escala;
  - a falta injustificada à prova vale 0.
- **Motor** (`tools/grading.py`, sem base de dados), com 7 grupos de casos dourados:
  - **ensino geral:**
    - MT = (MAC + NPT)/2;
    - MT3 das classes de exame = (MT1 + MT2 + MAC3)/3;
    - MFD = média das MT;
    - MFED = 0,6 × MT3 + 0,4 × EN (6.ª/9.ª) e 0,5/0,5 (12.ª);
  - **técnico:**
    - CT = (NPP + NPT)/2;
    - CF cumulativa, arredondada em cada passo;
    - CA = 60% CF + 40% PG nas disciplinas com prova global (3 ou mais tempos, fora das práticas);
    - opção «CA com CF precisa», como no secPed;
  - CF importada (migração);
  - CFD das disciplinas plurianuais;
  - classificação do curso: (2 × PC + PAP)/3 ou (4 × PC + EC + PAP)/6.
- **Janela de lançamento:**
  - trimestre fechado → só por reapreciação;
  - os trimestres fecham e reabrem por ordem;
  - a secretaria lança em qualquer trimestre aberto;
  - o professor lança só na sua disciplina, no trimestre em curso do ano em curso, ou com autorização (`edu.grade.edit.permission`);
  - a autorização exige motivo, dura até 30 dias, renova-se em vez de se duplicar e não serve para o trimestre em curso nem para um fechado.
- **Mini-pauta** (`edu.term.result`) e **pauta anual** (`edu.subject.result`): recalculadas a cada nota lançada.
- **Conselho de turma:**
  - caso limite: até 2 valores abaixo da aprovação;
  - o professor da disciplina dá +1 ou +2, ou o director abre uma votação de +2: nominal, sem abstenção, por maioria, e com quórum de 50% no técnico;
  - realizado o conselho, a pauta fecha e calculam-se as decisões.
- **Decisão de fim de ano** (`edu.year.result`):
  - resultados possíveis: transita, conclui, transita com disciplinas em atraso (exame extraordinário), admitido a exame de recurso, retido, pendente;
  - retido por faltas, ou no primário por frequência inferior a 2/3;
  - negativa em todas as disciplinas estruturantes → retido;
  - as disciplinas sem professor não contam para as negativas;
  - a decisão manual da direcção nunca é sobreposta;
  - a terceira retenção no nível exige decisão da direcção.
- **Exames especiais** (`edu.exam.requirement`):
  - recurso e extraordinário: a nota do exame substitui;
  - melhoria: prevalece a mais alta;
  - resolvidos todos os exames, a decisão actualiza-se.
- **Reapreciação** (`edu.grade.appeal`): uma só em curso por nota; é a única forma de alterar uma nota de um trimestre fechado, sempre dentro da cotação.
- **RDEC** da iniciação: avaliação qualitativa por área (Não satisfatório, Satisfatório, Bom, Muito bom).
- **Ligações à 5b:**
  - as disciplinas com notas não se retiram da matrícula;
  - a turma com notas não se renumera;
  - na rematrícula, o retido não sobe de classe;
  - com disciplinas em atraso, o aluno não entra na 9.ª nem na 12.ª e, nas outras classes, entra no máximo com 2.

## `edu_payroll`: carga lectiva nos salários
- Nos recibos dos professores pagos ao tempo: previstos no horário − aulas sem realização − aulas dadas por substitutos + substituições dadas + acerto.
- Os tempos previstos limitam-se ao mês, ao ano lectivo, ao trimestre do tempo e aos períodos de contrato.
- Um valor escrito à mão no recibo prevalece.
- Instala-se sozinho quando há horários e salários.

## Segurança
- Grupo **Professor**, no `edu_core`: aulas, chamada, notas e RDEC das suas turmas e disciplinas (e da turma que dirige); leitura dos alunos e das matrículas dessas turmas.
- Secretaria: tudo nas turmas. Direcção: decisões manuais, reabertura de trimestres e de conselhos, regimes de avaliação.

## Por fazer (5d e seguintes)
- Pautas, mini-pautas, termos e certificados impressos com o modelo oficial (5d).
- Épocas e sessões de exame, com vigilantes e salas (5d).
- Confirmar com a escola piloto a regra das classes de transição automática do primário (1.ª, 3.ª e 5.ª), que vem do secPed e não está no texto do RAA.
- Contagem das negativas terminais da classe anterior no técnico (resumo, IV.5) e a regra «mínimo 7 no ano terminal, sem negativa em dois anos seguidos».
