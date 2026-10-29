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
| Exclusão | MF < 7 ou assiduidade abaixo de 75 % (faltas injustificadas nas aulas dadas) |
| Recurso dos excluídos | não (configurável) |
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
- O resultado fica **na própria inscrição em UC** (há uma por UC; um modelo à parte só duplicava): MF, assiduidade,
  situação (dispensado, admitido, excluído), exame normal, recurso, especial, melhoria, nota final, origem da nota,
  créditos obtidos. As notas lançadas na grelha recalculam-no (o cálculo das médias trimestrais é desviado para
  aqui nas matrículas do superior); a situação por frequência fecha com o semestre (a anual, com o 2.º), a nota de
  exame decide logo.
- Motor puro em `tools/grading_higher.py`, com testes «golden» sobre o regulamento por defeito.

### Exames (7d)
- Épocas novas no `edu.exam.period`: **Época normal**, **Recurso**, **Época especial** e **Melhoria** (superior).
- Convocados de cada sessão pela situação da inscrição: normal = admitidos; recurso = admitidos não aprovados (quem
  reprovou ou faltou ao normal) e, se o regulamento deixar, os excluídos; especial = finalistas (opção) com até N
  UCs por aprovar no ano; melhoria = aprovados. A nota da pauta da sessão vai para o exame da inscrição; quem falta
  fica sem esse exame.

### Progressão e conclusão (7e)
- Reaproveita o **resultado do ano** (`edu.year.result`) e o fecho do ano: no superior a decisão sai das UCs. Passa
  sem atraso; passa com até N UCs obrigatórias por aprovar (do ano e dos anteriores); acima disso fica no mesmo ano e
  inscreve-se só nas UCs em falta; no último ano conclui com todas aprovadas. Com UCs por decidir fica pendente.
  A média do ano é pesada pelos créditos.
- O **TFC ou a dissertação** registam-se como a PAP (`edu.final.project`), com co-orientador e júri externo; a nota
  da defesa é a nota da UC do trabalho final.
- **Conclusão** (`edu.graduation`): média final do curso = média das UCs pesada pelos créditos (o trabalho final é
  uma UC), arredondada pelo regulamento; diploma numerado; certificado de habilitações com as UCs por ano e
  semestre, créditos, trabalho final e média; diploma com o grau e o curso.

### Portal, propinas, equivalências e demo (7f)
- **Emolumentos por UC:** as taxas do plano com gatilho (inscrição em UC em atraso, recurso, especial, melhoria)
  facturam-se ao estudante uma vez por inscrição, quando acontece; ficam fora da geração das propinas e do balcão.
- **Equivalências:** a direcção credita UCs aprovadas noutra instituição ou curso (transferência, migração), com
  nota, sem frequência nem exames; contam para a progressão e destravam as precedências.
- **Declaração com notas:** as UCs aprovadas até ao ano da matrícula, com créditos e média pesada (a meio do curso).
- **Portal do estudante:** o painel e «Minhas notas» mostram as UCs (provas e trabalhos, MF, presenças, situação,
  exames, nota final) e os créditos e a média do curso; sem portal do encarregado.
- **Turmas:** «2.º ano A · EI», não «2ª A».
- **Provas no portal:** as épocas do superior só aparecem a quem foi convocado.
- **Calendário de provas:** as épocas do superior criam-se do calendário académico (normal, recurso, especial,
  melhoria pelo nome do evento) e têm o botão «Convocar».
- **Documentos:** cabeçalho com o Ministério do Ensino Superior, Ciência, Tecnologia e Inovação; assinam o reitor e o
  responsável académico (cargo configurável na instituição); o diploma diz o grau conferido (Licenciado(a), Mestre).
- **Base de demonstração** `kututa_universidade` (Instituto Superior Kianda, fictício): Licenciatura em Engenharia
  Informática (4 anos, TFC) e Mestrado em Gestão de Sistemas de Informação (dissertação); 2025/26 fechado com
  notas reais (14 passam, 3 com UCs em atraso, 1 retido), 2026/27 com a 1.ª frequência lançada. Script em
  `tools/seed_demo_universidade.py`; os acessos ficam num ficheiro fora do repositório.

## Gate
Um estudante de licenciatura faz o ciclo completo sem encarregado: candidatura → matrícula → inscrição em UCs →
frequências → dispensa, exame e recurso → passagem com UCs em atraso → TFC → certificado. Os testes do motor batem
com os casos calculados à mão sobre o regulamento por defeito.

## Pendentes
- Confirmar o texto do certificado, do diploma e da declaração pelo modelo oficial de uma universidade (os PDFs já
  foram revistos: cabeçalho do MESCTI, reitor e responsável académico configuráveis, grau conferido, créditos).
- A facturação dos emolumentos só corre com a AGT ligada (como as propinas).
- Regulamento de uma universidade cliente, para afinar os valores por defeito.
- Doutoramento.
- Mapas para o MESCTI (estatísticas oficiais), quando houver modelo.
