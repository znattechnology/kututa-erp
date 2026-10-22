# Avaliação, documentos e histórico como no secPed

Data: 2026-10-22.

Origem: análise dos menus Autorizações de notas, Histórico do aluno, Diplomas e certificados, Declarações,
Avaliações e notas, Pautas, Imprimir pautas, Conselhos de turma, Resultados do ano, Reapreciações e
RDEC (iniciação), comparados com o secPed-Express. As cores ficam as do sistema.

Ficheiros do secPed onde está o modelo de cada parte:
- Documentos: `apps/web/components/academic/` (`declaracao-documents.tsx`, `diploma-document.tsx`,
  `certificate-document.tsx`, `termo-document.tsx`, `termo-curso-document.tsx`, `council-documents.tsx`,
  `rdec-document.tsx`, `rdea-document.tsx`).
- Serviços: `apps/api/src/modules/academic/application/services/` (`conclusion`, `conselho`, `acta`,
  `promotion`, `rdec`).

## 1. Documentos (prioridade)

### Declarações

1. **Dados de identificação no documento.** A secretaria completa no documento os dados que faltam na ficha
   (filiação, nascimento, naturalidade, província, BI, emissor e data, processo); ficam guardados no aluno. O
   documento conta os que faltam: «Estão todos preenchidos.» ou «Faltam N dados: na declaração saem como linha
   para preencher à mão.» Um dado em falta sai como uma linha, não como «—».
   Na Vovó Eva, nenhum dos 1697 alunos tem estes dados.
2. **Título e cabeçalho.** O título diz o tipo: «DECLARAÇÃO DE FREQUÊNCIA» ou «DECLARAÇÃO DE APROVEITAMENTO». O
   cabeçalho é o oficial: «REPÚBLICA DE ANGOLA», «MINISTÉRIO DA EDUCAÇÃO», a escola, o subtítulo e a morada.
3. **Texto.**
   - O regime vem a seguir ao número: «, em regime diurno» ou «pós-laboral».
   - A identificação acaba em «…, processo n.º …».
   - Escreve-se sempre «Província de …» e «emitido pelo Arquivo de Identificação … a …».
4. **Declaração de frequência.**
   - Aceita os anos passados (só recusa rascunho, anulada e transferida).
   - O tempo verbal muda: «Frequentou» num ano passado, «Está a frequentar» no ano em curso.
5. **Declaração com notas.**
   - Leva a média: «com o resultado final obtido X e a média de N (EXTENSO) VALORES».
   - Exige a decisão do ano. Sem ela: «Este aluno ainda não tem classificação final neste ano — feche o
     conselho de classe primeiro.»
   - Rótulos do resultado: Apto (transita, conclui, transita com atraso), Admitido a exame, Não apto,
     Pendente.
   - A nota de cada disciplina é a CFD, ou a classificação final quando não há CFD.
   - Duas assinaturas: o Subdirector Pedagógico e o Director Geral.
6. **Rodapé.**
   - Frequência: «Anexo V · Despacho n.º 60/08, de 30 de Abril · Válida enquanto durar a matrícula a que se
     refere.»
   - Com notas: «Anexo VI · Despacho n.º 60/08, de 30 de Abril · Classificações na escala de 0 a 20 valores,
     arredondadas às unidades.»
7. **OBS.** «A presente declaração destina-se a ____.» A linha fica em branco quando não há finalidade. A
   finalidade não tem valor por omissão.
8. **Menu.** «Declarações» mostra só as declarações (frequência, com notas, matrícula e transferência). O fluxo
   tem um passo: escolher o aluno, o tipo e o ano, completar os dados, ver a declaração e imprimir.
9. **Nova declaração de matrícula** (prefixo DM).
   - Texto: «Para os devidos efeitos, declara-se que o(a) aluno(a) <nome>, portador(a) da matrícula n.º <n>,
     se encontra regularmente matriculado(a) e a frequentar esta instituição de ensino no ano lectivo <ano>, na
     turma <t>, do curso de <c>.»
   - Fecho: «Por ser verdade e me ter sido solicitada, mandei passar a presente declaração, que assino e
     autentico com o carimbo em uso nesta instituição.»
10. **2.ª via.** A partir da segunda impressão, o documento leva «2.ª VIA».

### Diplomas e certificados

1. Botões «Diploma» e «Certificado» na lista e no formulário da conclusão. Cada um cria ou reaproveita o
   documento emitido e mostra-o.
2. Assistente «Registar conclusões» por turma da classe final: os alunos que concluíram, com a média e o
   estado, e o botão «Registar os N».
   - «Escolha a turma para ver quem tem a conclusão do curso.»
   - «Nenhum aluno da <turma> tem ainda a conclusão do curso. Aparecem aqui quando o conselho de classe a
     decidir.»
3. Verificar e assinar: «Verificado por» e «Assinado por» (o utilizador e a data, irreversíveis). Estado:
   «Por verificar», «Verificado, falta assinar», «Assinado». No formulário: «Quem marca fica registado como
   quem verificou ou assinou.»
4. Pesquisa: ano em curso, por verificar, assinados; agrupar por ano e por curso.
5. Texto do diploma e do certificado.
   - O regime e a Área de Formação vêm a seguir ao curso. A área é um campo novo do curso,
     `edu.course.training_area`.
   - O certificado mostra a fórmula: «Classificação final do curso = (2 × PC + PAP) / 3».
   - A data do diploma é a data de conclusão.
6. Lei de Bases no diploma: não copiar o artigo que o secPed cita sem confirmar com a escola.

### Histórico do aluno

1. Ecrã novo: um ano lectivo por linha.
   - Colunas: Ano | Turma (e curso) | Média final | Assiduidade | Resultado.
   - Resumo no topo, por exemplo «3 anos lectivos: transitou em 2 e concluiu o curso.»
   - Botões «Termo do curso» e, em cada ano, «Termo de <ano>».
   - Sem os botões do conselho.
2. Termo do ano (novo, sem número).
   - Título «REGISTO ACADÉMICO DO ANO», ou «TERMO DE FREQUÊNCIA E APROVEITAMENTO» na 9.ª classe.
   - Grelha: aluno, n.º, classe e turma, ano, curso, área, regime, assiduidade.
   - Tabela: Disciplina | CF (técnico) ou MFD | PG | CFD | F.J. | F.I.
   - Média final, resultado final e a assinatura do Director de Turma.
   - Legenda: «CF — Classificação de Frequência · PG — Prova Global · CFD — Classificação Final da
     Disciplina (do ciclo) · F.J./F.I. — Faltas justificadas/injustificadas.»
3. Termo do curso.
   - Impresso directamente do histórico.
   - Linhas «SITUAÇÃO NO FIM DO ANO» e «COMPORTAMENTO».
   - Rodapé com PC, EC e PAP.
   - Terceira assinatura: «O(A) Coordenador(a) de Turma».
   - Título «TERMO DE FREQUÊNCIA E APROVEITAMENTO DO CURSO TÉCNICO DE <CURSO>».
   - O regime e a área no cabeçalho.

### Solicitações (pedidos de documentos)

Modelo novo `edu.document.request`.
- Estados: pendente, em análise, aprovado, pronto, entregue, recusado, cancelado.
- Factura do preço do tipo, e só fica pronto depois de pago se a escola o exigir.
- Quitação ao entregar: «Entregar mesmo com pendências?»
- Prazo em dias úteis, com «Passou o prazo».
- Tipos de documento configuráveis.

## 2. Conselhos de turma, resultados do ano e RDEC

### Conselho de turma

1. **Passo «Iniciar».** O conselho começa no estado «Por iniciar».
   - Para o director: «Inicie o conselho para que os professores desta turma possam participar (votações,
     atribuição de pontos).»
   - Para os professores: «Aguarde que o director de turma inicie o conselho para poder participar.»
2. **Ecrã da turma.**
   - Grelha alunos × disciplinas: verde aprova, vermelho negativa, âmbar caso limite.
   - Clicar num caso limite: «Subir +2 (professor da disciplina)» ou «Abrir votação do conselho».
   - Cartões das votações abertas com «A favor», «Contra», «Apurar» e o quórum (técnico).
   - «Encerrar conselho».
3. **Votações.** Pode haver várias abertas ao mesmo tempo, mas só uma por nota.
   - «Quórum não atingido: votaram X de Y professores (mínimo Z). Recolha mais votos antes de apurar.»
   - «Aprovado (f/t) — +2 aplicado.» ou «Não aprovado (f/t).»
4. **Permissões.**
   - Só o director abre e apura as votações.
   - Só o professor da disciplina sobe os pontos (a direcção, como excepção).
   - Retirar pontos: o director, o professor da disciplina ou a direcção.
   - A secretaria só consulta.
5. **Acta do Conselho de Notas** (A4).
   - Título «ACTA DO CONSELHO DE NOTAS».
   - «Turma … · nível · Ano lectivo …»; «Director de Turma: … · Realizado em …».
   - Resumo: Alunos, Transita, Exame especial, Não transita, Reprovados por falta, Concluído, Pendentes.
   - «Aproveitamento por disciplina»: Disciplina | Professor | Alunos | Aprovados | % Aprov.
   - «Notas votadas pelo conselho»: Aluno | Disciplina | Nota (8 → 10) | A favor | Contra | Resultado.
   - «Assinaturas»: um professor por disciplina, com «<Disciplina> · x% aprovados».
6. **Lista de Presença — Conselho de Notas.** Tabela # | Professor | Disciplina | Assinatura.
7. **Manter do Kututa:** a direcção reabre o conselho, e as decisões calculam-se ao realizar.

### Resultados do ano

1. **Corrigir:** uma decisão manual de «transita» numa classe terminal deve gravar «Concluiu».
2. **Decisão manual por assistente:** qualquer estado, com fundamento obrigatório e a data da decisão.
3. **Relatório «Resultado final do ano».**
   - Vistas pivot e gráfico por nível, curso e turma.
   - Colunas: Com resultado, Aprovados, Aprovação (%), Média.
   - PDF.
4. **EEF** na lista para quem foi excluído por faltas. Agrupar por turma.

### RDEC (iniciação) e RDEA (primário)

1. **Documento RDEC.**
   - Título «RELATÓRIO DE DESEMPENHO ESCOLAR DA CRIANÇA».
   - Subtítulo «Educação Pré-Escolar / Iniciação · Avaliação qualitativa (Dec. Exec. 424/25)».
   - Identificação: criança, n.º, matrícula, turma, período, faltas.
   - Tabela Área | Nível | Observações, seguida da apreciação global.
   - Assinaturas: «O(A) Educador(a) / Director(a) de Turma» e «O(A) Director(a) Pedagógico(a)».
   - Rodapé: «A avaliação na Iniciação é exclusivamente formativa, diagnóstica e qualitativa, sem condições
     de retenção (Dec. Exec. 424/25, art. 19).»
2. **Regras.**
   - Só turmas de iniciação: «O RDEC destina-se apenas a turmas da Iniciação (Pré-Escolar).»
   - As áreas criam-se sozinhas a partir das disciplinas da matrícula.
   - Só o director de turma escreve.
   - Faltas do trimestre.
3. **Lista por turma e trimestre.**
   - Colunas: Nº | Criança | FJ | FI | avaliadas/total | Apreciação.
   - Botão «RDEC» na turma, que cria os relatórios em falta.
   - «Imprimir todos».
4. **RDEA (primário)** na impressão das pautas.
   - Título «RELATÓRIO DE DESEMPENHO ESCOLAR DO ALUNO».
   - Tabela Disciplina | MAC | NPT | MT | (MFD no último trimestre) | F.J. | F.I.
   - Média e situação.
   - Assinaturas: Director de Turma e Encarregado de Educação.
   - Legenda: «MAC — média das avaliações contínuas · NPT — nota da prova trimestral · MT — média do
     trimestre · MFD — média final da disciplina · F.J./F.I. — faltas justificadas/injustificadas.»

## 3. Notas, pautas, autorizações e reapreciações

1. **Grelha «Notas da turma»** (acção cliente; a falta mais importante).
   - Escolhe-se a turma e a disciplina na lista à esquerda.
   - Por trimestre, as colunas MAC·NPT·MT·FJ·FI no geral, ou NPP·NPT·CT·FJ·FI no técnico.
   - Depois as finais: CF ou MFD, [PG, CA], CFD, [EN, MFED].
   - «Editar notas» ↔ «Ver a pauta».
   - Faixa de aviso da janela de lançamento:
     - «Podes alterar o 1.º trimestre, que é o corrente.»
     - «O 2.º trimestre já foi encerrado: as notas só se corrigem por reapreciação.»
     - «Para mudar notas de outro trimestre, pede autorização à secretaria.»
     - Uma linha por autorização em vigor.
   - Resumo: «N positivas, N negativas, N sem nota final · média da turma».
   - A MT e a CT calculam-se enquanto se escreve.
   - As avaliações NPT, NPP, PG e EN criam-se sozinhas ao guardar.
   - Validação na hora, e «Guardar» bloqueado enquanto houver erros.
   - Teclado: Enter e as setas mudam de célula, «F» marca falta, Esc desfaz.
   - Barra «N alterações por guardar» com «Descartar» e «Guardar alterações».
   - O professor edita as suas disciplinas; o director vê todas; a secretaria edita qualquer trimestre aberto.
   - A segurança fica toda no servidor.
2. **Janela «Lançar MAC»** (geral): as avaliações contínuas do trimestre, «+ Nova avaliação» com o tipo
   (teste, trabalho, participação, oral, estágio), e a grelha de notas.
3. **Restrições.** Uma só NPT por turma, disciplina e trimestre; uma PG e um EN por turma e disciplina. Não há
   NPT no último trimestre das classes de exame do geral.
4. **Professor.** Vê só as avaliações das suas disciplinas (ou as da turma que dirige).
5. **Cor de negativa** pela nota de aprovação do regime, e não pelo valor fixo 10.
6. **Autorizações de notas.**
   - Formulário guiado: as turmas e as disciplinas do professor; trimestres abertos e não correntes.
   - «Vale até» é uma data e conta até ao fim desse dia.
   - Registo de quem deu e de quem revogou.
   - Filtro «Em vigor» e coluna «Situação».
   - Confirmação ao revogar.
7. **Reapreciações.**
   - Erro: «Deferir» sem nova nota grava 0.
   - Recusar quando a nova nota é igual à anterior («Para manter a nota, indefira.»).
   - A data da decisão fica registada.
   - Reapreciação também das médias importadas (`term_result_id`).
8. **Menus.** «Mini-pauta» abre a impressão. Os botões do conselho saem da lista das pautas; ficam no
   conselho.
