# Plano curricular e tempos semanais: Odoo × secPed × lei

**Data:** 2026-10-22. **Dados:** base `vovo_eva` (8 cursos técnicos de saúde, 10.ª–13.ª).

**Fontes legais (texto em `docs/referencias/avaliacao/`):**
- Despacho n.º 60/08 (técnico-profissional);
- Resumo do Regime de Avaliação 2026/2027 (documento do INP; não é lei);
- Decreto Executivo n.º 424/25 (ensino geral).

## 1. O que a lei pede ao plano
- **Técnico (Despacho 60/08):**
  - ciclo diurno 10.ª–12.ª (3 anos) ou pós-laboral 10.ª–13.ª (4 anos) (art. 6.º; arts. 43.º–44.º);
  - três componentes de formação (preâmbulo; certificado do Anexo IV):
    - sociocultural (Português, Inglês, FAI, Educação Física);
    - científica (Matemática e outras);
    - técnica, tecnológica e prática (com o Projecto Tecnológico);
  - disciplinas anuais, bienais ou trienais (art. 17.º, n.º 2);
  - prova global no fim de cada classe nas disciplinas com **3 ou mais tempos semanais** (art. 18.º, n.º 1). Não há prova global nas disciplinas técnicas só laboratoriais ou oficinais do Anexo I (n.º 3); a área da saúde não consta do Anexo I;
  - Projecto Tecnológico e PAP na 12.ª (diurno) ou na 13.ª (pós-laboral);
  - **não fixa** carga semanal total nem carga por componente, e não fala de estágio.
- **Resumo 2026/27:** ciclo de 4 anos com estágio curricular e classificação final (4·PC + EC + PAP)/6.
- **Ensino geral (DE 424/25):** não fixa a estrutura do plano. Os tempos servem para as faltas (art. 25.º).

## 2. O plano da Vovó Eva
- **Estrutura:** 8 planos activos, de 10.ª a 13.ª, todos com as três componentes. LP, ING, FAI, EF e MAT existem nos 8 cursos, e o Projecto Tecnológico está na 12.ª. Os dados são iguais aos do secPed.
- **Totais semanais:**

  | Classe | Tempos semanais |
  |---|---|
  | 10.ª | 32 |
  | 11.ª | 30 a 32 |
  | 12.ª | 26 (CPN) a 32 |
  | 13.ª | 0 (só o Estágio Curricular, com 0 tempos) |

- **A rever com a escola:**
  - **Práticas da 12.ª com 0 tempos** (PAC, PC, PE, PE2, PF, PF2, PND, PR3), mas com notas em 2025/26. Sem tempos, ficam sem limite de faltas e fora do horário e da carga do professor.
  - **50 linhas marcadas com prova global com menos de 3 tempos** (23 em AC, 27 em ENF: EF, Informática, QG, IEC, ING, Projecto Tecnológico…). Contrariam o art. 18.º, n.º 1. As marcas vêm das folhas de notas da escola.
  - **Horários de 2026/27 que não batem com o plano:**
    - EPIDEMIO nas 12.ª de AC;
    - EF na 10.ª C de FAR;
    - AFH (5 de 3) e FAI (1 de 3) na 10.ª F de FIS.
  - **Duração das disciplinas desactualizada** (EF, ING, LP, MAT, FARMACOL, PATOLOGI dizem 1 ano, mas aparecem em duas classes). Hoje não tem efeito: as regras usam as classes do plano.

## 3. Onde os tempos do plano entram nas regras

| Regra | De onde lê | Estado |
|---|---|---|
| Total da classe | soma das linhas | Certo |
| Horário × plano (aviso da turma, editor) | linha do plano da turma × aulas anuais | Certo |
| Faltas (técnico: 3 × tempos no ano; geral: 3/4/5) | linha do plano da turma (ou da classe anterior, nas disciplinas em atraso) | Certo. Com 0 tempos não há limite |
| Prova global | marca da linha do plano, proposta pela regra dos 3 tempos | Corrigido: já não se apaga ao mudar os tempos, e vê-se no plano |
| Disciplina terminal / plurianual | classes do plano em que aparece | Certo |
| Colocação do professor | linha do plano da turma (informativo) | Certo |
| Carga do professor | aulas do horário (máximo 24 − 4 − 2, regra do secPed) | Não usa o plano |
| Pautas, documentos, propinas | não usam tempos | — |

## 4. Corrigido nesta revisão
- **Apresentação:** a página do curso e o plano mostram a matriz como no secPed. Cada componente é um título com os seus tempos por classe, as disciplinas ficam por baixo e, no fim, «Tempos por semana».
- **Prova global:** a marca é proposta ao criar a linha e, depois, é da escola. Mudar os tempos ou a componente não a desfaz. A coluna «Prova global» aparece no plano.
- **Horário × plano:** o aviso passa a reagir quando uma aula muda de trimestre.

## 5. Decisões em aberto
1. **Exclusão por faltas no técnico:**
   - o Despacho (art. 12.º, n.º 1) diz que «produz efeitos só nessa disciplina»;
   - o Resumo do INP e o secPed excluem de todas;
   - hoje o Odoo retém o ano todo.
2. **Limite de faltas:** «o número máximo anual de faltas injustificadas é o triplo» (art. 12.º, n.º 2). Ao atingir o limite fica-se já excluído, ou só ao passá-lo? Hoje fica-se excluído ao atingi-lo.
3. **Estágio e classificação final:**
   - a política usa (2·PC + PAP)/3, mas a escola tem a 13.ª com estágio, a que corresponde (4·PC + EC + PAP)/6;
   - o estágio deve ser uma disciplina do plano ou um registo de estágio, não as duas coisas. Se for as duas, conta duas vezes.
4. **Prova global na componente técnica:**
   - a regra automática exclui a componente técnica inteira; a lei só exclui as disciplinas do Anexo I;
   - com a marca agora editável, a escola decide linha a linha;
   - falta decidir se a regra automática deve passar a seguir a lei à letra.
5. **Planos sem versão por ano lectivo:** mudar os tempos de uma linha muda retroactivamente os limites de faltas dos anos passados.
6. **Validações do plano:**
   - classes dentro do nível;
   - as três componentes no técnico;
   - exame nacional só no geral;
   - aviso para disciplinas com notas e 0 tempos.

   Só faz sentido validar cargas por componente com os planos curriculares oficiais, que não estão no repositório.
