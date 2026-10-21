# Regras de avaliação e transição: secPed-Express × Odoo (Secretaria Express)

**Data:** 2026-10-21.

**Fontes legais (texto em `docs/referencias/avaliacao/`):**
- Decreto Executivo n.º 424/25 (ensino geral);
- Despacho n.º 60/08 (técnico-profissional);
- Resumo do Regime de Avaliação 2026/2027.

**Código comparado:**
- secPed-Express, em `apps/api/src/modules/academic*`;
- `custom_addons/edu_evaluation`, `edu_attendance` e `edu_records` do Odoo.

## 1. De onde vem a decisão

| | secPed | Odoo |
|---|---|---|
| Parâmetros | Um sítio: `AcademicPolicyService.resolve(escola, nível, curso, ano, classe)`. Junta a `EvaluationPolicy`, a `PromotionRule` e a `GradeScale` por cima dos valores do MED | Um sítio: `edu.evaluation.policy._get(escola, nível)`. Uma política por escola e nível, criada com os valores da lei (`LEVEL_DEFAULTS`) e editável |
| Escolha do subsistema | O `nível` da turma. O técnico é sempre TECNICO; os outros usam `assessmentRegime`, que por omissão é GERAL | O campo `regime` da política (pré-escolar, primário, geral, técnico), que vem do nível |
| Fórmulas e decisão | Espalhadas por 6–7 serviços (notas, pauta, promoção, conselho, faltas, exames). Alguns decidem o regime por conta própria (`level !== "TECNICO"`, classe 6/9/12) | Um motor só, `edu_evaluation/tools/grading.py`: médias, CF, CA, MFED, bonificação e a árvore de decisão `decide()`. Os modelos (pauta, resultado do ano, conselho, exames) chamam esse motor com as regras da política |
| Excepções ao ponto único | O conselho de turma (`conselho.service.computeFinals`) calcula a nota com uma fórmula antiga, diferente da pauta e da promoção | As faltas escolhem a regra pelo `nível.subsistema` (técnico: 3 × tempos semanais no ano; geral: 3/4/5 por trimestre), não pela política |

**Conclusão.** No Odoo, a decisão vem de facto de um único sítio, um regime por escola e nível, com o motor `grading.py`. No secPed, só os parâmetros estão centralizados.

## 2. Comparação por subsistema

### Pré-escolar (iniciação)
- **Ambos:** avaliação qualitativa pelo RDEC (por área e trimestre), sem notas, e transição automática.
- **Igual.**

### Primário (1.ª–6.ª, Dec. 424/25, art. 21.º)

| Regra | Lei | secPed | Odoo |
|---|---|---|---|
| Escala / aprovação | 0–10 / 5 | 0–10 / 5 | 0–10 / 5 |
| MT | (MAC + NPT)/2 | 50/50, com arredondamento a 2 casas e depois às unidades | 50/50, um só arredondamento às unidades |
| Retenção | Qualquer disciplina < 5 | Tolerância zero (forçada) | Tolerância zero (sem transição condicional) |
| Frequência < 2/3 | Retido (art. 21.º, n.º 2, al. b) | Calcula, mas **não aplica** | **Aplica** (`min_attendance` 2/3) |
| 1.ª, 3.ª e 5.ª | Transição automática | Sim | Sim |
| 6.ª: MT3 e MFED | MT3 = (MT1 + MT2 + MAC3)/3; MFED com EN a 40% | Igual | Igual |
| 6.ª: recurso | Duas negativas entre 3 e 4, sem LP e MAT juntas (art. 31.º, n.º 5) | Comentário diz «tratado à parte»: não encontrado | **Até 3 negativas, sem nota mínima**: diverge da lei |

### Secundário geral, I e II ciclo (art. 25.º e 31.º)

| Regra | Lei | secPed | Odoo |
|---|---|---|---|
| 7.ª, 8.ª, 10.ª e 11.ª | **Transita** com até 2 negativas entre 7 e 9, sem LP e MAT juntas (II ciclo: LP + disciplina da área). As negativas vão a **exame extraordinário** no ano seguinte | 1–2 negativas → «CONDITIONAL», que no secPed é **recurso (II época), não transita**. LP+MAT só se a escola configurar | **Transita com disciplinas em atraso** e cria o exame extraordinário. Nota mínima 7, LP+MAT e LP+área. **Segue a lei** |
| 9.ª e 12.ª: MT3 e MFED | MT3 especial; EN a 40% (9.ª) e 50% (12.ª) | Igual (mas a regra da MT3 vale para qualquer turma das classes 6/9/12, sem olhar ao nível) | Igual, só nas classes de exame da política |
| 9.ª e 12.ª: recurso | **Até 3** negativas **entre 6 e 9**, sem LP e MAT juntas (12.ª: LP e/ou MAT + disciplina específica) | Banda de 2 por omissão; não modela as classes de exame | **Até 4** negativas e **sem nota mínima de 6**: diverge da lei |
| Faltas | 3/4/5 injustificadas por trimestre e disciplina (1/2/>2 tempos) → retido | Igual | Igual |
| Arredondamento | Às unidades | Duplo (2 casas, depois unidades) | Uma vez, às unidades |

### Técnico-profissional (Despacho 60/08 e Resumo 2026/27)

| Regra | Lei | secPed | Odoo |
|---|---|---|---|
| CT do trimestre | (NPP + NPT)/2 | Igual | Igual |
| CF | Cumulativa: CT2 = (CT1 + MT2)/2, CF = (CT2 + MT3)/2 | Igual (correcção da migração) | Igual |
| Prova global | ≥ 3 tempos, fora das práticas e do estágio; CA = 60% CF + 40% PG | Igual; uma PG lançada fora do conjunto elegível conta sempre | Igual; uma PG só se lança se a linha do plano tiver prova global (na Vovó Eva marcaram-se as 50 linhas onde a escola a faz) |
| Arredondamento da CA | Uma vez (medido: 98,6 % das folhas assinadas) | Uma vez | Uma vez (`technical_ca_precise`, ligado na Vovó Eva) |
| Transição 10.ª→11.ª, 11.ª→12.ª, 12.ª→13.ª | CA positiva a todas, **excepto no máximo duas** | Por omissão, 1–4 negativas → recurso; na Vovó Eva (`maxNegatives` = 2) ≤ 2 transita e 3–6 vão a recurso | ≤ 2 → **transita com disciplinas em atraso**; 3–5 → recurso; 6 ou mais → retido. **Segue o Resumo** |
| Recurso | Até 5 exames | Banda de 4 | Até 5 |
| Nota mínima nas negativas toleradas | 7 só no ano terminal da disciplina | 7 em todas | 7 em todas (**mais estrito do que o Resumo, a confirmar**) |
| Negativas de disciplinas terminais de classes anteriores contam | Sim (Resumo, IV.5) | Não modelado | **Não modelado** |
| Negativa em dois anos seguidos da mesma disciplina | Não pode (disciplinas plurianuais) | Não modelado | **Não modelado** |
| Sem classificação em dois trimestres → sem aproveitamento | Sim (Resumo, IV.7) | Não modelado | **Não modelado** (fica «pendente») |
| Disciplina sem professor não conta | Sim (Resumo, IV.6) | — | Sim |
| Faltas | Injustificadas no ano ≥ 3 × tempos semanais → excluído | Igual | Igual |
| CFD plurianual | Média das classificações anuais | Média das CF (o próprio secPed admite que devia ser das CA) | Média das classificações finais (CA com bonificação) |
| Classificação final do curso | (2 × PC + PAP)/3 | Igual | Igual; também (4 × PC + EC + PAP)/6 com estágio |

### Conselho de turma e exames (todos os subsistemas)

| Regra | secPed | Odoo |
|---|---|---|
| Caso limite e bonificação | +1/+2 a quem está 2 valores abaixo da aprovação; voto por maioria e quórum de 50 % no técnico | Igual |
| Tecto da bonificação | Sempre 20, também no primário (escala 0–10): erro | Tecto da escala do nível |
| Nota usada no conselho | Fórmula antiga (CF média simples, sem a CF anual, PG arredondada): pode decidir sobre uma nota diferente da pauta | A mesma nota da pauta |
| Recurso no técnico | A nota do recurso volta a passar pela CA com a PG (60/40): provável erro | A nota do recurso substitui a classificação |
| Classe terminal depois dos exames | Fica «transita», nunca «concluiu» | «Concluiu» |
| Decisão manual | Final, não se recalcula | Igual (só a Direcção) |

### Magistério
- **secPed:** sem regras próprias. Segue a política configurada (2 casas decimais, MAC a 40 %), e a regra da 12.ª do ensino geral aplica-se-lhe por engano.
- **Odoo:** usa o regime geral, com transição condicional em 10.ª–12.ª e recurso na 13.ª. Não há regulamento do magistério no repositório: **a confirmar**.

## 3. Correcções feitas no Odoo (2026-10-21)
1. **Recurso do ensino geral.**
   - **Nova regra:** campo novo «Mínimo das negativas para recurso» (`exam_floor`), aplicado em `grading.decide`.
   - **Valores da lei:**
     - 6.ª: até 2 negativas, entre 3 e 4;
     - 9.ª e 12.ª: até 3 negativas, entre 6 e 9.
   - **Migração:** a 20.0.1.1.0 do `edu_evaluation` actualiza as políticas que ainda tinham os valores antigos (3 e 4).
2. **Técnico (Despacho 60/08):**
   - **Transição:** com até duas negativas e sem nota mínima (`floor` 0).
   - **Negativas que vêm de trás:** contam as das disciplinas terminais das classes anteriores ainda por recuperar, dos anos em que o aluno transitou (`_prior_terminal_negatives`).
   - **Disciplina plurianual no ano terminal** (art. 28.º, n.º 2): passa a contar pela «nota para a transição» (`transition_grade`). É a CFD, ou uma negativa se faltarem os 7 valores do ano ou se houver negativa em dois anos seguidos. Só fica aprovada nessas condições.
   - **Sem classificação em dois trimestres:** depois de fechado o último trimestre, fica sem aproveitamento (retido) (`_ungraded_subjects`).
3. **Frequência mínima:** sai da política técnica (fica 0) e a migração do secPed deixa de a copiar para o técnico.

**Por fazer:**
- as faltas lerem o regime da política em vez do `nível.subsistema`;
- os pares proibidos no recurso da 12.ª: a lei proíbe «LP e/ou MAT com uma específica», mas o Odoo usa os pares da transição (LP+MAT e LP+área);
- o regulamento do magistério.
