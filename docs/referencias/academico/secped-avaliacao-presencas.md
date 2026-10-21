# Avaliação e presenças no secPed-Express: regras levantadas do código (2026-10-21)

Fonte: `secPed-Express/apps/api`, ficheiros `pauta-computation.service.ts`, `grade.service.ts`, `promotion.service.ts`, `conselho.service.ts`, `special-exam.service.ts`, `classificacao-frequencia.helper.ts`, `prova-global.helper.ts`, `council-adjustment.helper.ts`, `janela-lancamento.helper.ts`, `attendance.service.ts`, `teaching-load.service.ts` e `med-level-defaults.ts`.

Sempre que o código e o diploma divergem, o Kututa segue o diploma. As divergências estão no fim.

## Notas lançadas
- **Avaliações** (colunas) por turma, disciplina e trimestre. Cada avaliação tem um tipo, a cotação máxima (20 por omissão) e um peso.
- **Prova trimestral:** o tipo EXAME é a NP (geral) ou a NPT (técnico). Os outros tipos são avaliação contínua (MAC no geral, NPP no técnico).
- **Normalização:** uma nota numa avaliação com cotação inferior à escala é convertida para a escala (`nota / cotação × máximo da escala`). Nunca se reduz.
- **Arredondamento:** às unidades, metade para cima (9,5 → 10).

## Ensino geral (Dec. Exec. 424/25, Anexo III)
- **MAC** = média ponderada das avaliações contínuas, sem arredondar.
- **Classes de transição:** MT = R((MAC + NPT) / 2). O secPed arredonda primeiro a 2 casas e depois às unidades.
- **Classes de exame (6.ª, 9.ª, 12.ª), último trimestre:** MT3 = R((MT1 + MT2 + MAC3) / 3), sem prova trimestral.
- **Média final:** MFD = R(média das MT).
- **Exame nacional:** MFED = R(0,6 × MT3 + 0,4 × EN) na 6.ª e na 9.ª; 0,5/0,5 na 12.ª. Só nas disciplinas com exame nacional e só depois das três MT.
- **Primário:** escala 0–10, aprovação 5.
- **Iniciação:** sem notas; avaliação pelo RDEC (níveis Não satisfatório, Satisfatório, Bom, Muito bom).

## Técnico-profissional (Despacho 60/08)
- **CT de cada trimestre** = R(média das partes existentes entre NPP e NPT). A NPP é a média simples das contínuas.
- **CF cumulativa, arredondada em cada passo:** CT1 = MT1, CT2 = R((CT1 + MT2) / 2), CF = R((CT2 + MT3) / 2). Um trimestre sem nota deixa o acumulado como está.
- **CA** = R(0,6 × CF + 0,4 × PG). Sem prova global, CA = CF.
  - Na CA, o secPed usa a CF **sem arredondamentos intermédios**: por exemplo, (14,3344; 15) → 15, enquanto com a CF inteira 14 daria 14.
- **Prova global:** só nas disciplinas com 3 ou mais tempos semanais, que não sejam técnica/prática nem estágio. Também não há prova global em educação física, informática, desenho, prática, laboratório e oficina. A falta injustificada vale 0.
- **CF importada** (classificação anual, da migração): vence sobre a recomposição a partir dos trimestres.
- **CFD de uma disciplina plurianual:** no último ano = R(média das classificações anuais); antes do último ano fica por atribuir.
- **Classificação do curso:**
  - Dec. 90/04: (2 × PC + PAP) / 3;
  - resumo do INP: (4 × PC + EC + PAP) / 6;
  - PC = R(média das CFD).

## Valores por omissão por nível (`med-level-defaults`)

| Nível | Aprovação | Banda condicional | Transição automática | Escala |
|---|---|---|---|---|
| Iniciação | 2 (qualitativa) | 0 | sempre | 1–4 discreta |
| Primário | 5 | 0 | 1.ª, 3.ª e 5.ª | Insuf. 0–4, Suf. 5–6, Bom 7–8, Exc. 9–10 |
| Secundário I e II | 10 | 2 | — | Mau 0–5, Insuf. 6–9, Suf. 10–13, Bom 14–16, Exc. 17–20 |
| Técnico, magistério | 10 | 4 (técnico) | — | Insuf. 0–9, Suf. 10–13, Bom 14–16, Muito bom 17–20 |

Retenções: no máximo 2 por nível, fora do primário; a terceira exige decisão manual.

## Decisão de fim de ano (`promotion.decide`, por esta ordem)
1. Transição automática (iniciação, primário 1.ª/3.ª/5.ª) → transita.
2. Reprovado por faltas → retido.
3. Notas incompletas → pendente.
4. Negativa em todas as disciplinas estruturantes (lista por nível) → retido.
5. Sem negativas → transita (ou conclui, na classe terminal).
6. Alguma negativa abaixo do piso (aprovação − 3, isto é, 7) → retido.
7. Negativas dentro da banda condicional → condicional (exame de recurso por disciplina).
8. Caso contrário → retido.

Nunca se sobrepõe a uma decisão manual (final).

## Exames especiais (recurso, extraordinário, melhoria)
- Nota anterior = classificação final, ou a média das MT.
- Resultado = no exame de melhoria, o maior entre a nota anterior e a do exame; nos outros, a nota do exame.
- Resolvidos todos os exames: retido se algum falhou, senão transita.

## Conselho de turma
- **Caso limite:** aprovação − 2 ≤ base < aprovação (8 ou 9).
- **Bonificação:** o professor da disciplina dá +1 ou +2, ou o director de turma abre uma votação de +2.
  - A votação é nominal, sem abstenção e aprovada por maioria estrita.
  - Quórum de 50% dos professores no técnico.
- **Onde soma:** à CF no geral e à CA no técnico, com tecto no máximo da escala.
- Realizado o conselho, já não se altera.

## Lançamento de notas
- **Trimestre fechado:** não se lança nem se apaga; só por reapreciação. Os trimestres fecham por ordem.
- **Professor:** só lança no trimestre em curso do ano em curso, salvo com autorização da secretaria.
  - A autorização é por turma, disciplina e trimestre, com motivo de pelo menos 5 caracteres e prazo até 30 dias.
  - Não serve para o trimestre em curso nem para um trimestre fechado.
- **Secretaria e direcção:** lançam em qualquer trimestre aberto.

## Presenças
- **Estados:** presente, atraso (conta como presença), falta injustificada, falta justificada. Só a injustificada conta para os limites.
- **Limite no geral:** 3 faltas com 1 tempo semanal, 4 com 2, 5 com mais de 2, por trimestre e disciplina.
- **Limite no técnico:** 3 × tempos no ano, por disciplina. Exceder numa disciplina exclui de todas.
- **Situação:** em risco a uma falta do limite; reprovado ao atingir o limite.
- **Tempos semanais:** do plano curricular (o do curso primeiro, depois a classe mais próxima anterior).
- **Primário:** retido com frequência inferior a 2/3 das aulas (art. 21.º). O secPed não aplica esta regra.
- **Aulas:** uma por tempo do horário e data. As aulas canceladas não contam. Uma aula sem chamada não é falta.

## Carga lectiva paga
Final = máx(0, previstas − aulas sem realização − substituições feitas por outros + substituições dadas + acerto).
- As previstas são os dias do horário no mês, limitados ao trimestre do tempo e às datas do contrato.
- Exemplo: 4 segundas-feiras, 1 aula sem realização, 1 substituição feita por outro e 2 dadas → 4.

## Divergências do secPed corrigidas no Kututa
1. Ensino geral: o secPed tinha pesos 40/60 e arredondamento a 2 casas. O decreto e o Kututa usam 50/50 e unidades.
2. Na 12.ª classe, o exame nacional pesa 0,5.
3. Retenção por faltas: no secPed havia uma taxa global de 2/3. O Kututa aplica 3/4/5 por trimestre e disciplina e, no primário, a frequência de 2/3.
4. Primário: escala 1–10 e aprovação 5.
5. Transição com até 2 negativas entre 7 e 9, desde que não sejam ao mesmo tempo Português e Matemática (7.ª/8.ª) ou Português e a disciplina da área (10.ª/11.ª). As classes terminais exigem todas positivas.
6. O recálculo da classificação final depois de uma reapreciação usa a MT3, e não a média de todas as MT.
7. A base do conselho usa a mesma classificação que a pauta e a decisão.
8. O tecto da bonificação é o máximo da escala.
9. A reapreciação respeita a escala e a cotação.
10. As aulas canceladas não contam em nenhum mapa.
11. O trimestre da aula é deduzido da data.
