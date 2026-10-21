# Fase 5d: Secretaria Express, exames, arquivo e documentos oficiais (`edu_exam`, `edu_records`, `edu_documents`)

**Estado:** concluída a 2026-10-21. Testes: 4 no `edu_exam`, 4 no `edu_records` e 10 no `edu_documents`. A bateria dos 20 módulos tem 249 testes e 0 falhas. Instalado na base `kututa_demo`.

**Fontes:**
- modelos reais do Instituto «Vovó Eva» (técnico) e do Complexo L.B.D.F. (ensino geral), extraídos para `docs/referencias/academico/modelos-documentos.md`;
- anexos III a VII do Despacho 60/08;
- modelos `ExamPeriod`, `ExamSession`, `ExamRoom`, `ExamSupervisor`, `ExamSeating`, `Internship`, `FinalProject` e `GraduationRecord` do secPed.

## `edu_exam`: exames
- **Épocas:** provas trimestrais, provas globais, exame nacional, recurso, extraordinário, melhoria e época especial de conclusão. Uma época só se encerra com todas as sessões realizadas.
- **Sessões:** disciplina, turmas, data, hora, salas com lotação e vigilantes.
- **Conflitos:** a mesma sala, o mesmo vigilante ou o mesmo aluno em duas sessões à mesma hora.
- **Convocatória:**
  - nos exames especiais, os alunos com exame por fazer na disciplina;
  - nas provas, os matriculados nas turmas escolhidas.
- **Distribuição pelas salas:** por ordem alfabética, com número de lugar e dentro da lotação.
- **Fecho da sessão:**
  - nos exames especiais, as notas actualizam a pauta e a decisão;
  - nas provas, as notas vão para as avaliações ligadas;
  - falta injustificada = 0, mas quem falta à melhoria fica com a nota que tinha.

## `edu_records`: arquivo académico
- **Estágio curricular:** entidade, supervisor, tutor, horas e classificação.
- **PAP:** tema, orientador, júri, defesa e classificação.
- **Conclusão:**
  - só para quem concluiu (decisão «conclui», ou «transita» na classe terminal);
  - PC = média das classificações finais das disciplinas do curso, a CFD nas plurianuais;
  - classificação final pela fórmula da escola: (2 × PC + PAP)/3 ou (4 × PC + EC + PAP)/6;
  - a emissão exige a PAP e o estágio aprovados quando o curso os pede, e atribui o número de diploma sequencial na escola (ano/sequência);
  - regista o livro e a folha de termos.
- Número de processo individual do aluno (único na escola) e histórico escolar.

## `edu_documents`: documentos oficiais
- **Registo dos documentos emitidos:** número por tipo e ano lectivo (DSN/Nº01/2026-2027, DCN, DTR, GT, TFA, CH, DIP), finalidade, quem emitiu e quantas vezes se imprimiu. Cada documento verifica as suas condições: frequência com a matrícula em curso; notas com classificações finais; certificado e diploma com a conclusão emitida.
- **Modelos** (QWeb, com o texto dos modelos em uso):
  - declaração de frequência;
  - declaração com notas;
  - declaração para transferência: cabeçalho de Estado, visto e escola de tutela;
  - guia de transferência;
  - termo de frequência e aproveitamento: todas as classes do curso, no regime técnico (CT, PG, CA, REC, CFD) ou geral (MT, MFD, N.E, MF);
  - certificado de habilitações: técnico por componente, como o Anexo IV, ou geral por classe;
  - diploma (Anexo III);
  - mini-pauta e pauta da turma (mapa de aproveitamento final, em A3);
  - relação nominal, horário e cartão de estudante (CR80).
- **Formato:**
  - notas por extenso: «15 (QUINZE) VALORES», com catorze, dezasseis, dezassete, dezanove;
  - classes por extenso: «12ª (Décima Segunda) Classe»;
  - datas: «06 de Julho de 2026»;
  - concordância de género: filho/filha, nascido/nascida, O DIRECTOR/A DIRECTORA;
  - positivas a azul e negativas a vermelho (RAA, art. 35.º);
  - papel: A4 retrato, A4 paisagem e A3 paisagem.
- **Escola:** director e director pedagógico com o género, cargo, localidade dos documentos, linha oficial do cabeçalho, escola pública de tutela e licença.

## Notas
- No Odoo 20, o QWeb do servidor só passa ao modelo chamado as variáveis dadas como atributos do `t-call`. As definidas dentro do corpo já não chegam.
- O PDF exige o `wkhtmltopdf`: está na imagem Docker de produção, mas não na máquina de desenvolvimento. Em desenvolvimento usa-se a versão HTML (`/report/html/…`).

## Por fazer
- Logótipo e insígnia da escola nos dados da empresa (a demo usa o logótipo por omissão).
- Caderneta do professor e acta do conselho de turma (formato a acordar com a escola piloto).
- Os pedidos de documentos com prazo e preço ficam para a fase 6 (`edu_secretaria`), e a cobrança dos emolumentos para o `edu_fees` (5e).
