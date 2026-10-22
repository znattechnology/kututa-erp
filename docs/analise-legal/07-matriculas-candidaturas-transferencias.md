# Candidaturas, matrículas, confirmações, anulações e transferências: lei × secPed × Odoo

**Data:** 2026-10-22.

**Menus analisados** (secção Matrículas da secretaria):
- Candidaturas
- Lista de matrículas
- Nova matrícula
- Cancelamentos
- Transferências
- Rematrícula

**Sinais usados ao longo do documento:**
- **[T]**: texto legal lido;
- **[I]**: imprensa;
- **[P]**: prática ou interpretação.

## 1. Os diplomas que mandam

| Diploma | O que regula |
|---|---|
| **DP 162/23** | Ensino geral: idades, matrícula, confirmação, anulação, transferência (arts. 21.º–30.º) |
| **DP 167/23** | Técnico-profissional: idades e condições de acesso, vagas, provas de selecção, confirmação (arts. 22.º, 23.º, 48.º–52.º, 50.º) |
| **DE 424/25** | Matrícula condicional por disciplinas em atraso (art. 25.º) |
| **Despacho 60/08** | Técnico: matrícula e anulação por disciplina (arts. 8.º–11.º). Vigência incerta, mas aplicado na prática |
| **Calendário Escolar Nacional** (DE 686/25 para 2025/26) | Datas de inscrição, selecção, listas, reclamações, matrícula e reconfirmação |
| **DE Conjunto 40/21** | Taxas das escolas públicas do secundário. Pode ter sido substituído pelo DP 176/24 [I] |

Não se encontrou o «diploma próprio» das transferências (DP 162/23, art. 30.º, n.º 3).

## 2. Como deve funcionar, separador a separador

### 2.1 Candidaturas (acesso de novos alunos)

**O que a lei diz**
- **Idade mínima no ano da matrícula** [T]:
  - Ensino geral (DP 162/23, art. 21.º): Iniciação 5 anos; 1.ª classe 6; 7.ª classe 12; 10.ª classe 15.
  - Técnico (DP 167/23, art. 23.º): Média-Técnica 15 anos; Formação Profissional Básica 14 (até aos 17); Complementares 16 e 18; adultos 17.
- **Fora da idade regular** [T] (DP 162/23, arts. 22.º–23.º): aviso, e orientação para recuperação ou para educação de adultos.
- **Habilitação de acesso** [T]:
  - à 7.ª, o primário;
  - à 10.ª, o I Ciclo;
  - no técnico, o I Ciclo (DP 167/23, art. 22.º).
- **Técnico público** [T]:
  - vagas aprovadas pelo ministério (o privado é livre, art. 48.º);
  - prova de selecção obrigatória na Média-Técnica (art. 49.º);
  - admitido só com ≥ 10 em cada prova, mesmo que sobrem vagas, ordenado pela nota até esgotar as vagas (art. 52.º);
  - com excesso de candidatos, desempate por idade e média.
- **Fases do calendário** [T]: inscrição → teste → listas → reclamações → matrícula.

**secPed**
- Separador «Por decidir» com os dias de espera e comprovativo com QR.
- Na aprovação sugere a turma pelo curso, pela classe e pela ocupação, e cria o aluno, o encarregado e a matrícula numa só operação.
- Não tem exame, vagas por curso, idade, documentos nem prazos.
- Duplica os encarregados e não detecta candidatos repetidos.

**Odoo**
- Fluxo `draft → submitted → review → approved/rejected` e aprovação com escolha da turma.
- Reutiliza o aluno pelo BI.
- Não tem: idade, habilitação, vagas por curso, prova, lista de colocados, prazos, comprovativo, sugestão de turma.
- A turma não se limita ao curso e à classe pretendidos.
- O ano por omissão é o corrente, quando as candidaturas são para o ano seguinte.
- Uma candidatura aprovada pode apagar-se.
- Na Vovó Eva há 0 candidaturas.

**Como deve funcionar**
1. A candidatura é para o **ano seguinte**, durante a fase de inscrição do calendário. Valida a idade (bloqueia abaixo do mínimo, avisa fora da idade regular), a habilitação e os documentos entregues (lista por nível, pela «certidão/BI, fotografias, certificado de habilitações» do art. 26.º).
2. O curso tem vagas por ano. No técnico público, prova de selecção: lança-se a nota, admite-se com ≥ 10 e ordena-se pela nota. A **lista de colocados** é publicada e imprimível, com prazo de reclamação.
3. Admitido → **matrícula** na fase de matrícula: cria o aluno, o encarregado (procurado pelo BI ou telefone, sem duplicar), a matrícula e as disciplinas, com o comprovativo. A turma é sugerida, e a candidatura fica protegida contra eliminação.

### 2.2 Lista de matrículas e Nova matrícula

**O que a lei diz**
- **Documentos da 1.ª matrícula** [T] (art. 26.º): primário com 2 fotografias; secundário com certificado de habilitações, BI e 4 fotografias.
- **Processo incompleto** [T]: 60 dias após o início do ano, a matrícula é anulada (art. 24.º, n.º 10).
- **Fora de prazo** [T]: só até ao fim do 1.º mês do II trimestre, com justificativo e vaga (art. 25.º, n.º 2).
- **Declarações falsas** [T]: anulam a matrícula com todos os efeitos (art. 28.º, n.º 2).
- **Crianças sem documentos** [I] (despacho do MED, 2026): matrícula provisória.
- **Turmas** [T] (art. 10.º): até 36 alunos (45 por excepção; 26 com necessidades especiais).
- **Matrícula condicional** [T] (DE 424/25, art. 25.º): até 2 disciplinas em atraso na 9.ª e na 12.ª, que só fica efectiva com aprovação no exame extraordinário até ao I trimestre.
- **Técnico** [T]: matrícula por disciplina (Despacho 60/08, arts. 9.º e 10.º).

**secPed**
- Lista paginada com separadores de estado.
- «Nova matrícula» é na prática a renovação aluno a aluno, com a classe-alvo pela decisão do ano anterior e as turmas sugeridas.
- Aplica no servidor «retido não avança», os atrasos na 9.ª e na 12.ª e o bloqueio de dívida.
- Ignora o aviso de dívida no ecrã e não tem comprovativo de matrícula.

**Odoo**
- Lista com filtros (abre no ano em curso), confirmação com o n.º de matrícula vitalício e o n.º de ordem, vagas, regras de retenção, atrasos e dívida.
- «Nova matrícula» é um formulário vazio, que aceita turmas de anos fechados.
- **Nenhuma matrícula fecha no fim do ano**: os estados «Concluída» e «Retido» só existem por migração.
- Duas regras diferentes para «uma matrícula por ano».
- Barra de estado incompleta.
- Não tem documentos exigidos, prazos nem matrícula condicional real (as disciplinas em atraso não entram na matrícula).

**Como deve funcionar**
1. **Lista:** o ano em curso por omissão, com os estados, o tipo (nova, confirmação, repetente, transferido) e o painel por curso e turma.
2. **Nova matrícula** é só para quem **entra** sem candidatura (casos excepcionais). Abre no ano em curso, só com turmas abertas desse ano. Pede os documentos e fica «**Pendente — processo incompleto**» até os ter. Aviso aos 60 dias e anulação oficiosa ao fim deles.
3. **Fora do prazo** do calendário: só até ao 1.º mês do II trimestre, com motivo e vaga.
4. **Matrícula condicional:** as disciplinas em atraso entram na matrícula com a marca «condicional», ligadas ao exame extraordinário. A matrícula só fica efectiva quando forem aprovadas.
5. **Fecho do ano** (conselho de turma ou pautas finais): cada matrícula passa a «Concluída» ou «Retida», conforme o resultado do ano. É isto que alimenta a confirmação.
6. **Comprovativo/ficha de matrícula** imprimível, com o processo individual (art. 27.º).

### 2.3 Rematrícula (confirmação de matrícula)

**O que a lei diz**
- **Confirmação automática** [T] (DP 162/23, arts. 24.º, n.º 2 e 27.º, n.º 3; DP 167/23, art. 50.º, n.º 4): é responsabilidade da escola, os encarregados não precisam de se deslocar, e não pode depender da entrega de documentos.
- **Excepções** [T]:
  - 9.ª→10.ª: é nova matrícula, não confirmação (n.os 8 e 9);
  - reprovado por faltas no secundário: só depois de justificadas, até à 2.ª semana; a escola confirma em ≤ 5 dias úteis (n.os 3 e 5);
  - II Ciclo reprovado por faltas injustificadas: sem direito a matrícula no ano seguinte, só exame (n.º 4).
- **Calendário** [T]: «reconfirmação automática» em Julho, e as turmas formam-se logo depois dos resultados finais.
- **Taxa de confirmação** nas escolas públicas do secundário (DE Conjunto 40/21). O primário público é gratuito (Lei de Bases, art. 11.º).

**secPed**
- Não há confirmação em massa: é aluno a aluno.
- As matrículas ficam activas ao fechar o ano.

**Odoo**
- Assistente turma → turma (uma de cada vez) e as turmas do ano seguinte têm de já existir.
- Propõe retidos para a classe seguinte.
- **Um aluno bloqueado desfaz o lote inteiro.**
- Não diz quem fica de fora.
- Na Vovó Eva, **33 alunos de 2025/26 não têm matrícula em 2026/27**, e nenhuma lista os mostra.

**Como deve funcionar**
1. **Preparar o ano seguinte:** criar as turmas a partir das do ano que acaba (mesmo curso, classe + 1, mesmos nomes, capacidade e turno), numa só operação.
2. **Confirmação automática por escola:** para cada aluno com a matrícula fechada:
   - Concluída/transita → classe seguinte;
   - transita com disciplinas em atraso → classe seguinte, com matrícula condicional;
   - Retido → mesma classe (repetente);
   - reprovado por faltas → **fica pendente** até haver justificação;
   - concluiu o curso, transferido ou anulado → fica de fora;
   - 9.ª→10.ª → fica de fora (nova matrícula).

   A turma de destino é a correspondente (10.ª A → 11.ª A) ou a menos cheia.
3. **O resultado é uma lista**, não um erro:
   - confirmados;
   - pendentes, com o motivo (faltas por justificar, turma cheia, dívida em modo bloquear, limite de retenções);
   - excluídos, com o motivo.

   Os pendentes resolvem-se um a um e cada caso falha sozinho.
4. A **dívida** segue a política da escola (avisar ou bloquear), mas os documentos nunca condicionam a confirmação (art. 27.º, n.º 3). A taxa de confirmação vem do plano de propinas e não se cobra no primário público.
5. Painel **«Falta confirmar»**: os alunos do ano anterior sem matrícula no ano em curso.

### 2.4 Cancelamentos (anulação de matrícula)

**O que a lei diz**
- **Ensino geral** [T] (DP 162/23, art. 28.º):
  - a pedido do encarregado (ou do aluno maior) **até ao fim do II trimestre**;
  - motivos justificados: doença, mudança de residência, actividades oficiais > 45 dias lectivos;
  - a anulação justificada no II Ciclo dá direito a **exames especiais**.
- **Anulação oficiosa** [T]: processo incompleto aos 60 dias, ou declarações falsas.
- **Técnico** [T] (Despacho 60/08):
  - ciclo de formação: anulação **por disciplina** até ao 5.º dia útil do III trimestre (art. 11.º);
  - 9.ª de transição: uma disciplina anula todas (art. 8.º);
  - quem anulou pode fazer exame na época normal (art. 39.º).
- **Na pauta** [T] (DE 424/25, art. 35.º; Termos do Despacho 60/08): «Anulação de matrícula» é um resultado próprio, escrito a azul, e não é reprovação.

**secPed**
- Lista das anuladas com resumo por ano e «Reactivar» só no ano corrente.
- Ao reactivar apaga a data e o motivo (perde-se o rasto).
- Anular não cancela as facturas.
- Permite anular uma transferida.

**Odoo**
- Assistente com data e motivo em texto livre.
- Não tem prazo, lista de motivos, anulação por disciplina, nem efeitos nas propinas.
- «Reactivar» não volta a passar as regras.
- O nome muda de sítio para sítio: o menu diz «Cancelamentos», o estado diz «Anulada».
- A lista não mostra as transferidas nem filtra por ano.

**Como deve funcionar**
1. **Um só nome:** «**Anulações de matrícula**», que é o termo da lei.
2. **O pedido regista:**
   - quem pede (encarregado, aluno maior ou oficiosa);
   - o motivo, de uma **lista da lei** (doença, mudança de residência, actividades oficiais, processo incompleto, declarações falsas, outro) mais as observações;
   - se é justificado.
3. **Prazos:** até ao fim do II trimestre no ensino geral. No técnico, por disciplina até ao 5.º dia útil do III trimestre. Fora do prazo, só a direcção.
4. **Efeitos:**
   - deixa de gerar propinas;
   - as facturas futuras ficam canceladas, mas as vencidas mantêm-se;
   - na pauta aparece «Anulou a matrícula» a azul;
   - anulação justificada no II Ciclo → direito a exames especiais;
   - as notas e as faltas ficam no processo.
5. **Reactivar** volta a passar todas as regras e mantém o histórico no registo de alterações (não se apaga).

### 2.5 Transferências

**O que a lei diz** [T] (DP 162/23, art. 30.º; aplica-se ao técnico por analogia)
- Autorizadas por razões plausíveis.
- **Só se concluem depois de a escola de destino confirmar a vaga.**
- **A escola de origem envia o processo individual** (notas, faltas, disciplina; art. 29.º).
- O aluno fica «Transferido» na origem, a azul na pauta.
- Entrada fora de prazo até ao 1.º mês do II trimestre.
- Taxa de transferência no secundário público (DE Conjunto 40/21).

**secPed**
- Tipos em linguagem corrente: mudar de turma, mudar de curso, sair para outra escola.
- Destino filtrado pela mesma classe, com lugares visíveis.
- Dossier de saída (guia em carta, certificado de notas, registo académico) só depois de concluída.
- Mas: a mudança de curso não refaz as disciplinas nem as propinas, não há separação entre quem pede e quem aprova, e não há transferência de entrada.

**Odoo**
- 4 tipos (`internal` = mudança de turma), aprovar → concluir.
- A mudança interna refaz as disciplinas.
- A guia emite-se mesmo antes de a transferência estar concluída.
- Não tem vista de pesquisa nem filtros.
- Rejeitar não exige motivo.
- **Não há transferência de entrada.**
- Na Vovó Eva há 0 transferências registadas: as 8 «TRANSFERIDO» vieram só como motivo na matrícula.

**Como deve funcionar**
1. **Três casos** com os nomes do secPed:
   - Mudar de turma (mesma classe e curso);
   - Mudar de curso (mesma classe; refaz as disciplinas **e o plano de propinas**);
   - Sair para outra escola.
2. **Saída:**
   - pedido com o motivo e a escola de destino;
   - registo da **confirmação de vaga** pela escola de destino (data e documento);
   - só depois se conclui;
   - na conclusão: matrícula «Transferido», facturas futuras canceladas, dossier (guia, certificado de notas, registo académico) emitido e com o bloqueio de dívida da escola aplicado;
   - na pauta aparece «Transferido» a azul.
3. **Entrada** (novo):
   - aluno vindo de outra escola, com a guia e o processo;
   - cria-se ou reutiliza-se o aluno, e regista-se a escola de origem e as classificações trazidas;
   - matrícula do tipo «transferido», permitida até ao 1.º mês do II trimestre e só com vaga.
4. **Separação de funções:** a secretaria pede, a direcção aprova. Rejeitar exige motivo. Lista com filtros por estado, tipo e ano, e o «próximo passo» de cada pedido.

## 3. Problemas encontrados nos dados da Vovó Eva

1. **Sem 11.ª classe em 2026/27** (a escola teve uma só turma de entrada por ano até 2025/26):
   - 483 alunos da 12.ª aparecem como matrícula nova;
   - 20 alunos têm a matrícula anterior a apontar para uma retenção antiga. A regra «retido não avança» bloqueá-los-ia se a matrícula fosse reconfirmada.
2. **Disciplinas em atraso:** 187 alunos da 13.ª «transitaram com disciplinas em atraso» e as 228 provas especiais estão todas por fazer. 3 alunos têm 3 disciplinas em atraso, acima do limite de 2.
3. **33 alunos de 2025/26 sem matrícula em 2026/27:** 26 retidos, 5 «transita» e 2 com atrasos.
4. **0 facturas** emitidas apesar de haver planos de propinas em 2026/27, e a matrícula e a confirmação não se cobram.
5. **Datas e ordem:** todas as matrículas de 2026/27 têm a data 01/09/2026; há um buraco no n.º de ordem da turma 243.

## 4. Proposta de implementação, por fases

| Fase | Conteúdo | Porque primeiro |
|---|---|---|
| **A. Fecho e confirmação do ano** | Fechar as matrículas pelo resultado do ano; criar as turmas do ano seguinte; confirmação automática por escola com a lista de confirmados, pendentes e excluídos; painel «Falta confirmar» | É a lei (confirmação automática), é o maior trabalho de Setembro, e sem o fecho nada do resto funciona no fim de 2026/27 |
| **B. Anulações** | Nome único, motivos da lei, quem pede, prazos, efeitos nas propinas, «Anulou» a azul nas pautas, reactivar com as regras | Regras da lei claras e baratas de aplicar |
| **C. Transferências** | Três casos, confirmação de vaga, entrada de transferidos, dossier só depois de concluída, filtros, separação de funções | A entrada não existe hoje |
| **D. Matrícula e candidatura** | Idades e habilitação por nível, documentos e «processo incompleto» (60 dias), prazos do calendário, matrícula condicional real, comprovativo; no técnico público: vagas, prova, lista de colocados | Mais dados a parametrizar (calendário, documentos, vagas) |

**Decisões necessárias antes de codificar:**
- **Datas:** se o calendário escolar é configurado pela escola ou carregado por ano (há valores por omissão do DE 686/25).
- **Processo incompleto:** se a anulação aos 60 dias é automática ou só um alerta à direcção.
- **Taxas:** se são públicas (tabela do DE Conjunto 40/21, zonas A/B) ou livres (privado). Ficam parametrizáveis no plano de propinas.
- **Vigência do Despacho 60/08:** confirmar com a escola se a anulação e a matrícula por disciplina no técnico continuam a aplicar-se (a vigência é incerta).
