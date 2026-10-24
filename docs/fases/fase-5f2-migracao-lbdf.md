# Fase 5f (2.ª escola): migração do Complexo Escolar Privado L.B.D.F

**Estado:** concluída a 2026-10-24. A escola foi migrada do secPed-Express (`secped_dev`, *slug* `lbdf`) para uma base própria, `lbdf`, como a Vovó Eva (uma base por cliente). É a primeira escola do **ensino geral**: Iniciação, Primário (1.ª–6.ª), I Ciclo (7.ª–9.ª) e II Ciclo (10.ª–12.ª, Ciências Físicas e Biológicas e Ciências Económico-Jurídicas).

O porquê das decisões do lado do secPed (extracção das pautas, fusão de identidades, veredictos inferidos) está em `secPed-Express/docs/MIGRACAO-LBDF.md`.

## Resultado
- **Pauta: 16 700 de 16 700 iguais e 0 diferentes.** A classificação do ano no Odoo é a que o secPed mostra, com a MFD assinada e, nas classes de exame, a MF assinada.
- **335 disciplinas-aluno sem nota final no secPed.** São pautas em falta ou vazias; também ficam incompletas no Odoo.
- **Contagens iguais às do secPed:**
  - 1 728 alunos;
  - 3 093 matrículas;
  - 50 professores;
  - 979 aulas do horário.

## Como correr
```bash
SECPED_DSN=postgresql://…@localhost:5432/secped_dev SECPED_ESCOLA=lbdf SECPED_SAIDA=/fora/do/repositorio \
    .venv/bin/python odoo/odoo-bin shell -c config/odoo.conf -d lbdf --no-http < tools/migrar_secped.py
```
A base `lbdf` foi criada em dois passos:
1. `-i base --load-language=pt_AO`, e depois a empresa em Angola com a moeda AOA;
2. os mesmos módulos da `vovo_eva`, com o plano de contas `ao`.

## O que mudou para o ensino geral
- **Exame nacional e MF assinada.**
  - A pauta das classes de exame (6.ª, 9.ª e 12.ª) tem MFD, NE, MF e REC.
  - O NE entra como avaliação «Exame nacional» do 3.º trimestre, com as notas, em todas as disciplinas em que a escola o lançou.
  - A MF (ou a nota do recurso, que a substitui) entra em `edu.subject.result.imported_final` (novo, no `edu_evaluation`) e vence a MFED calculada.
  - A escola calcula `MF = 0,4 × MFD + 0,6 × NE`, enquanto o Dec. 424/25 manda `0,6 × MT3 + 0,4 × EN` (6.ª e 9.ª) e `0,5/0,5` (12.ª). Vale a assinada.
- **Reconciliação por regime.** No técnico, `secped_final` (CA = 60% CF + 40% PG). No geral, `secped_general_final`: a MF arredondada nas classes de exame; a MFD arredondada, mais a bonificação, nas outras.
- **Tolerância de negativas.** No geral, a migração já não escreve por cima o `maxNegatives` do secPed (0 no Secundário). Fica a do RAA (2, art. 25.º), que é a que a escola aplica.
- **Planos antigos.** A 6.ª de 2023/24 (7 disciplinas) e a 12.ª de 2023/24 (Filosofia) têm na pauta assinada disciplinas que o plano actual da escola já não tem. As turmas desse ano ficam com uma cópia arquivada do plano, «<plano> (2023/2024)», com essas disciplinas. O plano do curso, e portanto o das turmas novas, continua a ser o actual.
- **Turnos.** O turno da Manhã foi alargado às 12:35, o fim do último tempo da escola.
- **Iniciação.** As turmas chamam-se «Iniciação A», e não «0ª A» (`edu_core`).
- **Escola de tutela.** A escola de tutela e a sua directora vão para a ficha da escola (`edu_documents`), para os certificados e declarações com notas. O diploma de criação (Decreto Executivo n.º 2796/2026) fica nos avisos, porque ainda não há campo para ele.
- **Contas.**
  - **Pessoal (53 contas):** 50 professores, 2 da Direcção e a Secretaria.
  - **Alunos (1 042 contas):** os 1 042 alunos de 2026/27 que têm acesso no secPed ficam com conta na Área do Estudante (`edu_portal`). Os alunos que só existem nos anos fechados ficam apenas com a ficha.
  - **Palavras-passe:** nenhuma conta tem palavra-passe; define-a quem administra.

## Achados (para a escola)
| Achado | Casos | O que fica no Odoo |
|---|---|---|
| Decisão assinada diferente do cálculo do regime | 101 de 1 895 | A decisão assinada, como manual. Os casos mais frequentes são:<br>• retenções na 1.ª, 3.ª e 5.ª, que pelo RAA são de transição automática (31);<br>• «Transita» onde o cálculo dá retido (26), recurso (7) ou pendente (6) |
| Pendente no secPed (recurso sem matrícula seguinte, por exemplo) | 80 | A decisão calculada (44 recurso, 24 transita, 7 conclui, 5 retido) |
| Choques de professor no horário de 2026/27 | 77 | Ficam como estão. No Primário, o horário do secPed é por classe e repete-se em todas as turmas |
| Grelhas sobrepostas na Manhã (Primário e Secundário) | 7 tempos | As aulas ficam com as suas horas, sem tempo da grelha associado |
| Classes de exame sem disciplinas marcadas com exame nacional no plano | todas | Marcadas a 2026-10-24 as obrigatórias da 6.ª (7), da 9.ª (13) e da 12.ª (11 por área), como a escola fez nas pautas assinadas, que têm NE em todas as obrigatórias. As extracurriculares ficam sem exame. O Dec. 424/25 (art. 13.º) remete a lista para um edital anual do Ministério: confirmar com o edital de 2026/27. Os anos fechados não mudam |

O resto do que está pendente do lado da escola mantém-se como no secPed: identidades duvidosas, professores em falta, fichas incompletas, datas reais dos trimestres e logótipo.

## Testes
`TestEduMigrationGeneral`: uma escola geral em memória, com a 9.ª fechada e a Iniciação em curso. Cobre:
- o exame nacional e a MF assinada, que vence a MFED;
- a reconciliação a zero;
- a disciplina do plano antigo, na cópia arquivada do plano;
- a tolerância de negativas do RAA;
- o nome «Iniciação A»;
- a escola de tutela;
- a conta só para o aluno com acesso.
