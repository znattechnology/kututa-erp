# Fase 7: `edu_university` (ensino superior)

## Objectivo
Pôr uma universidade ou instituto superior angolano a funcionar sobre o que já existe (fases 5 e 6), com licenciatura e
mestrado. Não se duplica nada: a escola continua a ser a empresa, o curso o `edu.course`, a unidade curricular o
`edu.subject`, a matrícula o `edu.enrollment`, a avaliação o `edu.assessment`/`edu.grade`, as épocas o
`edu.exam.period`, as propinas facturas AGT do `edu_fees`. O módulo novo só acrescenta as regras próprias do superior.

## Decisões (utilizador, 29/10/2026)
| Tema | Decisão |
|---|---|
| Regras de avaliação | **Regulamento académico configurável por instituição**, com valores típicos de origem; cada universidade ajusta |
| Ciclos | **Licenciatura e mestrado** (doutoramento fica para depois) |
| Progressão | **Por UC, com limite de atraso**: passa de ano com até N UCs em atraso; repete só as reprovadas, com precedências |
| Encarregado | **Opcional**: o estudante é, em regra, maior e o adquirente das suas facturas |

## Base normativa
- **Decreto Presidencial n.º 193/18** (Normas Curriculares Gerais dos cursos de graduação): unidades curriculares
  semestrais, obrigatórias, optativas ou transversais; TFC obrigatório (arts. 47.º e 48.º).
- **Calendário académico geral do subsistema de ensino superior**: dois semestres de 21 semanas (16 de aulas e
  avaliação contínua, 5 de exames das épocas normal e de recurso); época especial em Setembro.
- **Regulamentos académicos de cada instituição** (UTANGA, UPRA, UniLuanda, UAN…): dispensa, admissão a exame,
  recurso, época especial, melhoria, prescrição. Variam, daí o regulamento configurável.

## Valores típicos de origem (regulamento por defeito)
| Regra | Valor |
|---|---|
| Escala / aprovação | 0–20 / 10 |
| Média de frequência (MF) | média ponderada das provas de frequência e trabalhos do semestre |
| Dispensa de exame | MF ≥ 14 (a MF é a nota final) |
| Admissão a exame normal | 7 ≤ MF < 14 |
| Exclusão | MF < 7 ou assiduidade abaixo de 75 % |
| Nota final com exame | 40 % MF + 60 % exame (configurável; 0 % = só o exame) |
| Mínimo no exame | 10 (configurável; abaixo reprova mesmo com MF alta) |
| Recurso | quem reprovou ou faltou ao normal; mesma fórmula, com a nota do recurso |
| Época especial | até 2 UCs para conclusão de curso; nota positiva fixa em 10 (opção) |
| Melhoria | uma vez por UC, no ano seguinte; fica a melhor |
| Passagem de ano | até 2 UCs em atraso (configurável), contando as do ano e as anteriores |
| Prescrição | 3 inscrições na mesma UC (configurável) |
| Créditos por semestre | 30 (aviso acima; limite configurável) |
| Média final de curso | média das UCs ponderada pelos créditos, arredondada às unidades |

## Desenho
### Estrutura (7a)
- `edu.level`: subsistema novo **`higher`** e níveis **Licenciatura (LIC)** e **Mestrado (MES)**.
- `res.company`: subsistema **Ensino superior**, código no MESCTI no lugar do código do MED.
- Ano académico com **dois semestres**: reaproveita-se `edu.trimester` (período lectivo); numa instituição superior
  o ano tem 2 períodos chamados «1.º Semestre» e «2.º Semestre», com o mesmo fecho do período.
- Plano curricular: cada linha (UC) ganha o **semestre** (1, 2 ou anual), os **créditos**, as **horas de contacto** e o
  **tipo** (obrigatória, optativa, transversal). As precedências já existem (`edu.subject.prerequisite_ids`).
- TFC (licenciatura) e dissertação (mestrado) entram no plano como UC própria do último ano, marcada como
  trabalho final.

### Encarregado opcional (7a)
- Na instituição superior o encarregado não se pede na candidatura nem aparece no processo do estudante; pode
  ligar-se um, se existir (patrocinador, pai que paga).
- A factura já vai para o estudante quando ele tem NIF ou não há encarregado (`edu_fees`); mantém-se.

### Inscrição por UC (7b)
- A matrícula anual no curso continua a ser o `edu.enrollment` na turma do ano.
- **`edu.uc.registration`** (inscrição em UC): matrícula, UC, semestre, turma onde a frequenta (pode ser de outro
  ano, no caso das UCs em atraso), n.º da inscrição (1.ª, 2.ª…), estado (inscrito, aprovado, reprovado, anulado).
- Na matrícula geram-se as inscrições das UCs obrigatórias do ano e das UCs em atraso; as optativas escolhem-se.
- Verificações: precedências aprovadas, créditos do semestre, prescrição.

### Avaliação (7c)
- **`edu.university.regulation`**: o regulamento por instituição e nível (valores acima).
- Avaliações e notas: reaproveita-se `edu.assessment`/`edu.grade` e a grelha de notas, por turma, UC e semestre, com
  os tipos «Prova de frequência» e «Trabalho».
- **`edu.uc.result`** (resultado na UC, um por inscrição): MF, situação (dispensado, admitido, excluído), exame
  normal, recurso, especial, melhoria, nota final, aprovado, créditos obtidos.
- Motor puro em `tools/grading_higher.py`, com testes «golden» sobre o regulamento por defeito.

### Exames (7d)
- Épocas novas no `edu.exam.period`: **Época normal**, **Recurso**, **Época especial**, reaproveitando a Melhoria.
- Os candidatos de cada sessão saem dos resultados (admitidos ao normal, reprovados para o recurso…); a nota lançada
  na pauta da sessão alimenta o `edu.uc.result`.

### Progressão e conclusão (7e)
- Resultado do ano: passa se as UCs em atraso (do ano e anteriores) não excederem o limite; senão fica no mesmo ano
  e inscreve-se só nas UCs em falta.
- **`edu.thesis`** (TFC ou dissertação): tema, orientador, co-orientador, júri, data e acta da defesa, nota.
- Conclusão: todas as UCs e o trabalho final aprovados; média final ponderada pelos créditos; certificado de
  habilitações, diploma e declaração com notas pelos relatórios do `edu_documents`.

### Portal, propinas e demo (7f)
- Portal do estudante: UCs inscritas, notas, créditos, exames e propinas; sem portal do encarregado.
- Propinas mensais pelo `edu_fees`; emolumentos a pedido (inscrição em UC em atraso, exame de recurso e especial,
  melhoria, certificado).
- Base de demonstração `kututa_universidade` com uma licenciatura e um mestrado.

## Gate
Um estudante de licenciatura faz o ciclo completo sem encarregado: candidatura → matrícula → inscrição em UCs →
frequências → dispensa, exame e recurso → passagem com UCs em atraso → TFC → certificado. Os testes do motor batem
com os casos calculados à mão sobre o regulamento por defeito.

## Pendentes
- Regulamento de uma universidade cliente, para afinar os valores por defeito.
- Doutoramento.
- Mapas para o MESCTI (estatísticas oficiais), quando houver modelo.
