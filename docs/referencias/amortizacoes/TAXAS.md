# Reintegrações e amortizações em Angola: regime fiscal e taxas

Documento de referência para o módulo `l10n_ao_asset`. Pesquisa feita em 2026-10-20.

Neste documento, **[OFICIAL]** marca o que foi lido no texto legal (no PDF do Diário da República, por OCR, ou em transcrição integral fiel). **[SECUNDÁRIO]** marca o que vem de consultoras ou escritórios de advogados. **[INTERPRETAÇÃO]** marca leituras nossas que ainda precisam de validação por um contabilista ou consultor fiscal.

---

## 1. Fontes legais

| Diploma | O que regula | Fonte consultada |
|---|---|---|
| **Decreto Presidencial n.º 207/15, de 5 de Novembro** (DR I Série n.º 152, de 05/11/2015, pág. 3854 e ss.). Aprovado em 23/09/2015, assinado em 23/10/2015 | Regime de reintegrações e amortizações e **Tabela das Taxas** (anexo). Revoga a Portaria n.º 755/72 | PDF oficial (digitalizado): https://files.lex.ao/presidente-da-republica/2015/decreto-presidencial-n-o-207-15-de-05-de-novembro/download/decreto-presidencial-n-o-207-15-de-05-de-novembro_presidente-da-republica_lex-ao.pdf · Ficha: https://lex.ao/docs/presidente-da-republica/2015/decreto-presidencial-n-o-207-15-de-05-de-novembro/ · Texto e tabela transcritos: https://angolex.com/paginas/decreto-presidencial/regime-das-reintegracoes-e-amortizacoes-207a-15a.html |
| **Código do Imposto Industrial (CII)**, Lei n.º 19/14, de 22 de Outubro | Arts. 24.º a 44.º (amortizações) | https://angolex.com/paginas/codigos/codigo-do-imposto-industrial.html |
| **Lei n.º 26/20, de 20 de Julho** (altera o CII) | Nos arts. 24.º a 44.º só altera o **art. 40.º, al. e)**: o limite das viaturas ligeiras passa a Kz 20 000 000 | https://angolex.com/paginas/codigos/alteracao-do-codigo-do-imposto-industrial.html |
| Lei n.º 27/22, de 22 de Agosto (altera o CII) | Só altera o art. 73.º (taxa do regime simplificado). **Não toca nas amortizações** | https://angolex.com/paginas/codigos/alteracao-do-codigo-do-imposto-industrial-27a-22a.html |
| Decreto n.º 6/96, de 26 de Janeiro | Reavaliação do imobilizado corpóreo (citado no art. 26.º, n.º 3 do CII) | Não consultado |
| Lei do OGE 2026 / Circular n.º 1 GACA/GJ/AGT/2026 | Não renova o regime de neutralidade fiscal das reavaliações livres de 2023/2024 **[SECUNDÁRIO: EY]** | https://www.ey.com/content/dam/ey-unified-site/ey-com/pt-ao/services/tax/documents/tax-alert-especial-lei-orcamento-geral-do-estado-2026.pdf |

As cópias locais (dados não confiáveis, guardados só para referência) estão em `fontes/`:

- `DP_207_15.pdf`: PDF oficial digitalizado, 16 págs. Inclui também outros diplomas do mesmo DR.
- `DP_207_15_ocr.txt`: OCR desse PDF (tesseract, por), com erros típicos de OCR (`8,33` aparece como `833`, `50` como `so`, `8` como `g`).
- `angolex_207_15.*`, `lexao_207_15.*`, `angolex_cii.*`, `angolex_lei26_20.*`, `angolex_lei27_22.*`: páginas HTML e o texto extraído delas.
- `secundarias/ey_oge2026*.pdf`: alertas fiscais da EY Angola sobre o OGE 2026.

Não foi encontrado nenhum Decreto Executivo que actualize a tabela (art. 9.º do DP 207/15) nem o limite de Kz 30 000 (art. 36.º, n.º 3 do CII). Também não foi encontrado nenhum novo Código do Imposto Industrial em vigor. A ausência não está provada: deve ser confirmada no Diário da República ou com um consultor antes de entrar em produção.

---

## 2. Regras gerais

### 2.1 Método

- **Quotas constantes (linha recta) é o método obrigatório** (CII art. 27.º, n.º 1; DP 207/15 art. 6.º, n.º 2). As taxas da tabela são **taxas anuais** pelo método das quotas constantes e **deduzem-se da vida útil** (taxa = 100 / vida útil). **[OFICIAL]**
- Outro método (por exemplo, degressivo) só com **aprovação prévia** da AGT/DNI mediante requerimento fundamentado. Sem essa aprovação, o custo não é aceite (CII art. 27.º, n.º 2; DP art. 6.º, n.º 3). **[OFICIAL]**
- Cada bem usa o **mesmo método** desde a entrada em funcionamento até estar totalmente amortizado, ser transmitido ou inutilizado (CII art. 28.º). **[OFICIAL]**
- **Intangíveis: sempre quotas constantes** (CII art. 39.º, n.º 5). **[OFICIAL]**

### 2.2 Taxas máximas e mínimas

- As taxas da tabela são **limites máximos** para efeitos fiscais (DP art. 4.º; CII arts. 24.º, n.º 1, 40.º, al. c) e 42.º). O excesso não é custo fiscal. **[OFICIAL]**
- **Não há taxa mínima legal.** Ainda assim, a amortização só é aceite se estiver **contabilizada no próprio exercício** (CII art. 25.º, n.º 3 e art. 40.º, al. a)). A quota que não for contabilizada num ano não se recupera mais tarde. **[OFICIAL; a parte da "perda" é INTERPRETAÇÃO]**
- **Regularização (art. 41.º):** a amortização que exceda o máximo num exercício pode ser aceite como custo no exercício seguinte, se for feita a regularização contabilística adequada. **[OFICIAL]**
- **Escolha da secção da tabela (DP art. 6.º, n.os 4 a 7):** aplica-se a taxa do sector de actividade do contribuinte. Se o bem ou a actividade não constar da tabela, aplica-se a **Secção G** ("elementos comuns"). Um bem sem taxa em nenhuma secção precisa de requerimento e deferimento expresso da AGT. **[OFICIAL]**
- **Laboração intensiva (CII art. 30.º):** a quota de imobilizado corpóreo pode ser acrescida de **+25%** com 2 turnos e de **+50%** com laboração contínua. **[OFICIAL]**

### 2.3 Início da amortização, duodécimos e fim de vida

- A amortização começa na **entrada em funcionamento ou início de utilização**. Considera-se que isso acontece quando o bem é contabilizado como activo amortizável. **O imobilizado em curso não se amortiza** (DP art. 3.º, n.os 2 e 3; CII art. 25.º, n.º 2). **[OFICIAL]**
- **Regra base (CII art. 29.º, n.º 1):** as quotas são calculadas por **períodos anuais**, contados a partir do **ano** em que o bem começa a ser utilizado. **[OFICIAL]** Lido à letra, o ano de entrada em funcionamento leva uma quota anual completa. **[INTERPRETAÇÃO: a confirmar com consultor]**
- **Opção pelos duodécimos (CII art. 29.º, n.º 2):** o contribuinte pode calcular por períodos mensais. Nesse caso, quota mensal = quota anual / 12, a partir do **mês** de entrada em funcionamento (o mês de entrada conta inteiro). **[OFICIAL]**
- **Último ano de vida útil (art. 29.º, n.º 3):** com duodécimos, aceita-se até ao mês em que termina a vida útil. **[OFICIAL]**
- **Venda ou abate antes do fim da vida útil (art. 29.º, n.º 4):** aceitam-se as amortizações até ao **ano** ou ao **mês anterior** ao da transmissão ou inutilização, conforme o regime seguido. O mês (ou ano) do abate **não** leva quota. **[OFICIAL]**
- **Fusões, cisões e trespasses (art. 29.º, n.º 5):** os bens continuam com o mesmo método e o mesmo período que tinham na entidade de origem. **[OFICIAL]**
- **Transitório:** o DP 207/15 aplica-se a bens que entraram em funcionamento a partir do exercício de **2015**. Os bens anteriores mantêm o regime anterior (Portaria 755/72) (DP art. 10.º; CII art. 44.º). **[OFICIAL]**

> Sugestão para o Odoo: em `account.asset`, usar o método `linear`, o período "mensal" (duodécimos) e a data de início = 1.º dia do mês de entrada em funcionamento (`prorata_computation_type = 'none'` com a data no dia 1, ou o equivalente). Disponibilizar como alternativa o regime "anual, ano completo". No abate, não deve haver quota no mês do abate.

### 2.4 Bens de reduzido valor

- Activos cujo custo unitário **não exceda Kz 30 000,00** podem ser **totalmente amortizados no exercício** em que entram em funcionamento (CII art. 36.º, n.º 1). **[OFICIAL, texto original da Lei 19/14, não alterado pela Lei 26/20]**
- **Excepção:** bens que fazem parte de um conjunto que deve ser amortizado como um todo e que não podem ser avaliados e usados individualmente (art. 36.º, n.º 2). **[OFICIAL]**
- O limite pode ser alterado por Decreto Executivo do Ministro das Finanças (art. 36.º, n.º 3). **Não foi encontrada nenhuma actualização**, por isso o valor de Kz 30 000 deve ficar como parâmetro configurável no módulo. **[OFICIAL + nota]**

### 2.5 Bens adquiridos em estado de uso

- São amortizados pelo **período de utilidade esperado**, que a DNI/AGT pode corrigir (CII art. 34.º, n.º 1). **[OFICIAL]**
- Se se souber o ano da primeira entrada em funcionamento, o período **não pode ser inferior** a (vida útil da tabela − anos de uso já decorridos) (art. 34.º, n.º 2). **[OFICIAL]**
- Os mapas de amortização devem indicar o número provável de anos de utilização dos bens adquiridos em estado de uso (art. 43.º, n.º 1, al. f)). **[OFICIAL]**

### 2.6 Reavaliação

- Valorimetria: custo de aquisição ou de produção, ou **custo revalorizado** nos termos do **Decreto n.º 6/96**, ou da legislação que o substitua (CII art. 26.º). **[OFICIAL]**
- As amortizações de bens reavaliados ao abrigo de legislação fiscal são aceites **nos termos dessa legislação**. As quotas sobre o acréscimo de uma reavaliação **não autorizada por lei fiscal** (reavaliação livre ou contabilística) **não são custo fiscal** (art. 37.º). **[OFICIAL]**
- Em 2023 e 2024 houve um regime (via OGE) de **reavaliações livres fiscalmente neutras**. Esse regime **não foi renovado** para 2025 e seguintes (OGE 2026). **[SECUNDÁRIO: EY Angola]**
- Implicação para o módulo: guardar separadamente o custo histórico e o acréscimo de reavaliação, e marcar se a reavaliação é fiscalmente aceite. Isto permite calcular a diferença fiscal (o acréscimo vai ao quadro de correcções da Modelo 1).

### 2.7 Imobilizado incorpóreo

- Não se aceitam amortizações de incorpóreos **sem deperecimento efectivo** (CII art. 39.º, n.º 1). **[OFICIAL]**
- Com deperecimento efectivo e **período determinável**: amortiza-se nesse período, com um máximo dado pela norma IAS 38 (CII art. 39.º, n.º 2; DP art. 5.º). **[OFICIAL]**
- Período **não determinável**: **5 anos** (20%) (art. 39.º, n.º 3). **[OFICIAL]**
- **Programas informáticos (software)** contabilizados como incorpóreo, adquiridos ou desenvolvidos internamente: **3 anos** (33,33%) (art. 39.º, n.º 4). **[OFICIAL]**
- Na tabela do DP 207/15, a **Secção N** tem **uma só linha**: N.1, despesas de I&D, incluindo propriedade industrial (patentes, marcas, alvarás e processos de fabrico), **20% / 5 anos**. Isto foi confirmado no PDF oficial. **[OFICIAL]**
- **Trespasses (goodwill) e despesas de constituição não aparecem na tabela.** **[INTERPRETAÇÃO]** O goodwill, por regra, não tem deperecimento efectivo (art. 39.º, n.º 1), logo não seria amortizável fiscalmente. As despesas de constituição ou instalação, se ainda reconhecidas como incorpóreo pelo PGC, cairiam nos 5 anos do art. 39.º, n.º 3. **Confirmar com consultor.**

### 2.8 Outras regras com impacto no módulo

- **Terrenos não se amortizam**, salvo se estiverem afectos exclusivamente à exploração e só na parte sujeita a deperecimento. Se um imóvel for comprado sem valor do terreno discriminado, presume-se que o terreno vale **20% do valor global** (CII art. 31.º). **[OFICIAL]**
- **Viaturas ligeiras de passageiros ou mistas:** a amortização sobre a parte do custo (inicial ou revalorizado) que exceda **Kz 20 000 000** não é aceite. A excepção são viaturas afectas a transporte público ou a aluguer, quando essa é a actividade normal (CII art. 40.º, al. e), na redacção da Lei 26/20. O valor anterior era Kz 7 000 000). **[OFICIAL]**
- Barcos de recreio, aviões e helicópteros: as amortizações não são aceites, salvo se afectos a transporte ou aluguer (art. 40.º, al. f)). **[OFICIAL]**
- Bens móveis sujeitos a registo sem declaração de venda ou identificação do bem: as amortizações não são aceites (art. 25.º, n.º 4). **[OFICIAL]**
- **Obras em propriedade alheia e grandes reparações:** amortizam-se no período de utilidade esperado (art. 35.º). **Locação financeira:** o bem é amortizado pelo locatário (art. 32.º). **Activos revertíveis em concessões:** amortizam-se pelo prazo que resta da concessão, se este for menor que a vida útil (art. 33.º). **[OFICIAL]**
- **Desvalorizações excepcionais:** amortização extraordinária com requerimento até ao fim do mês seguinte ao facto. Há deferimento tácito ao fim de 45 dias (art. 38.º). **[OFICIAL]**
- **Mapas de reintegrações e amortizações (art. 43.º):** devem indicar os anos e valores de aquisição e de reavaliação, as grandes reparações, as amortizações acumuladas e as do exercício, os abates justificados, o valor residual e os anos de utilização dos bens usados ou reavaliados. Acompanham a Modelo 1 (art. 40.º, al. h)). **[OFICIAL]** O módulo deve produzir este mapa.
- **Instituições financeiras e seguradoras** seguem o respectivo normativo contabilístico (art. 24.º, n.º 3). **[OFICIAL]**

---

## 3. Tabela de taxas (anexo ao DP 207/15)

A tabela está organizada por secções da CAE, de **A a N** (A: agricultura; B: pesca; C: indústrias extractivas; D: indústrias transformadoras, subsecções DA a DN; E: electricidade, gás e água; F: construção; **G: comércio, serviços gerais e elementos comuns**; H: alojamento e restauração; I: transportes, armazenagem e comunicações; J: telecomunicações e TI; K: actividades financeiras; L: saúde; M: outros serviços; N: activo incorpóreo).

A tabela completa está em **`taxas.csv`**: **477 linhas, todas conferidas com o PDF oficial**. Colunas: `code,group,name,rate,source,life_years`. O código é `<secção>.<número do item>`, por exemplo `G.4.1.2`. A taxa está em %, com ponto decimal.

### 3.1 Secção G: elementos comuns (secção por defeito, DP art. 6.º, n.º 5)

| Código | Descrição | Taxa % | Vida útil (anos) |
|---|---|---|---|
| **1. Edifícios e outras construções** | | | |
| G.1.1 | Edifícios industriais | 4 | 25 |
| G.1.2 | Edifícios industriais sujeitos a corrosão | 5 | 20 |
| G.1.3 | Edifícios comerciais e administrativos | 4 | 25 |
| G.1.4 | Edifícios habitacionais | 2 | 50 |
| G.1.5 | Edifícios destinados exclusivamente a serviços de saúde, de ensino e a serviços recreativos e culturais | 4 | 25 |
| G.1.6 | Construções ligeiras em fibrocimento, madeira, metais, etc. | 12,5 | 8 |
| G.1.7 | Obras hidráulicas, incluindo poços de água | 10 | 10 |
| G.1.8 | Obras de pavimentação | 10 | 10 |
| G.1.9 | Pontes e aquedutos em betão ou alvenaria | 3,33 | 30 |
| G.1.10 | Pontes e aquedutos metálicos | 8,33 | 12 |
| G.1.11 | Pontes e aquedutos em madeira | 20 | 5 |
| G.1.12 | Silos, reservatórios e outros depósitos | 5 | 20 |
| G.1.13 | Muros | 6,67 | 15 |
| G.1.14 | Vedações ligeiras (madeira, arame, etc.) | 25 | 4 |
| G.1.15 | Arranjos urbanísticos | 25 | 4 |
| G.1.16 | Via-férrea (actividade ferroviária) | 2 | 50 |
| G.1.17 | Pontes e obras de arte (actividade ferroviária) | 2,5 | 40 |
| **2. Instalações** | | | |
| G.2.1 | De água, electricidade, ar comprimido e refrigeração central (inclui cogeração) | 10 | 10 |
| G.2.2 | Redes de cabos aéreos e respectivos suportes | 6,67 | 15 |
| G.2.3 | Postos de transformação | 10 | 10 |
| G.2.4 | Ascensores, monta-cargas e escadas mecânicas | 10 | 10 |
| G.2.5 | De captação e distribuição de água (privativas) | 12,5 | 8 |
| G.2.6 | De carga, descarga e embarque (privativas) | 7,14 | 14 |
| G.2.7 | Centrais telefónicas e outras comunicações | 16,66 | 6 |
| G.2.8 | De distribuição de combustíveis líquidos | 10 | 10 |
| G.2.9 | De segurança, detecção e extinção de incêndios | 12,5 | 8 |
| G.2.10 | Instalações divisórias em escritórios | 20 | 5 |
| G.2.11.1 / .2 / .3 | Armazenagem e depósito: de betão / de madeira / metálicas | 5 / 20 / 12,5 | 20 / 5 / 8 |
| G.2.12 | Reservatórios para combustíveis líquidos | 6,66 | 15 |
| G.2.13 | Refeitórios e cozinhas privativas | 10 | 10 |
| G.2.14 | Vitrinas e estantes fixas | 20 | 5 |
| G.2.15 | Vitrinas, estantes e expositores móveis | 33,33 | 3 |
| G.2.16 / G.2.17 | Estações / Apeadeiros (ferroviária) | 4 | 25 |
| G.2.18 | Instalações não especificadas | 10 | 10 |
| **3. Máquinas, equipamentos e aparelhos** | | | |
| G.3.1 | **Computadores e outros equipamentos para tratamento de informação (hardware)** | 33,33 | 3 |
| G.3.2 | Equipamentos electrónicos de automatização, regulação e supervisão | 20 | 5 |
| G.3.3 | Máquinas de cópia (fotocopiadoras, scanners, fax) | 25 | 4 |
| G.3.4 | Impressoras | 33,33 | 3 |
| G.3.5 | Televisores, plasmas, monitores, projectores de vídeo | 25 | 4 |
| G.3.6 | Outras máquinas e equipamentos electrónicos | 20 | 5 |
| G.3.7 | Máquinas e equipamentos de conservação e manutenção | 12,5 | 8 |
| G.3.8 | Motores, incluindo geradores | 25 | 4 |
| G.3.9 | Máquinas-ferramentas ligeiras | 20 | 5 |
| G.3.10 | Máquinas-ferramentas pesadas | 12,5 | 8 |
| G.3.11 | Material contra incêndios (extintores e outros) | 25 | 4 |
| G.3.12 | Aparelhos de ar condicionado e ventilação | 12,5 | 8 |
| G.3.13 | Aparelhos de laboratório e precisão | 14,28 | 7 |
| G.3.14 | Aparelhos de medida e controlo | 12,5 | 8 |
| G.3.15 | Telefones fixos | 16,67 | 6 |
| G.3.16 | Telefones móveis | 33,33 | 3 |
| G.3.17 | Máquinas, equipamentos e aparelhos não especificados | 12,5 | 8 |
| **4. Veículos e outros meios de transporte** | | | |
| G.4.1.1 | Veículos automóveis **pesados** | 16,67 | 6 |
| G.4.1.2 | Veículos automóveis **ligeiros** | 25 | 4 |
| G.4.1.3 | Veículos automóveis **mistos** | 20 | 5 |
| G.4.2 | Veículos funerários | 20 | 5 |
| G.4.3 | Tractores e atrelados, empilhadores e camiões basculantes | 14,28 | 7 |
| G.4.4 | **Bicicletas e motociclos** | 25 | 4 |
| G.4.5 a G.4.8 | Barcos: de ferro / madeira / borracha / fibra de vidro | 7,14 / 10 / 12,5 / 20 | 14 / 10 / 8 / 5 |
| G.4.9 / G.4.10 / G.4.11 | Locomotivas e automotoras / Vagões / Vias-férreas | 5 / 4 / 4 | 20 / 25 / 25 |
| G.4.12 | Aeronaves | 5 | 20 |
| **5. Mobiliário, ferramentas e utensílios** | | | |
| G.5.1 | Artigos de conforto e decoração | 20 | 5 |
| G.5.2 | Equipamento publicitário na via pública | 12,5 | 8 |
| G.5.3 | Filmes, discos e cassetes | 25 | 4 |
| G.5.4 | Material de desenho e topografia | 12,5 | 8 |
| G.5.5.1 | **Mobiliário de madeira** | 16,67 | 6 |
| G.5.5.2 | **Mobiliário de outros materiais** | 12,5 | 8 |
| G.5.6 | Moldes, matrizes, formas e cunhos | 25 | 4 |
| G.5.7 / G.5.8 | Taras e vasilhame: de madeira / de metal | 20 / 14,28 | 5 / 7 |
| G.5.9 | Contentores | 8,33 | 12 |
| G.5.10 | Encerados | 50 | 2 |
| G.5.11 | **Ferramentas e utensílios de oficinas** | 14,28 | 7 |
| G.5.12 | **Outras ferramentas e utensílios** | 25 | 4 |

As notas a) "Taxa igual à hotelaria e restauração" e b) "Inclui armazéns feitos destes materiais; os armazéns em betão ou alvenaria entram nos edifícios" aparecem no fim da Secção G, ponto 2. **O PDF não mostra a que linhas se referem os marcadores (a)/(b).** A nota b) parece aplicar-se a G.1.6 (construções ligeiras). **[INCERTO]**

### 3.2 Outras secções relevantes (excertos; o resto está no CSV)

| Código | Descrição | Taxa % | Vida |
|---|---|---|---|
| H.1.1 | Edifícios exclusivamente para hotelaria e restauração | 4 | 25 |
| H.1.2 | Decorações interiores, incluindo tapeçarias (exclui móveis e arte antigos) | 25 | 4 |
| H.1.6 | Mobiliário de quartos, salas e salões (hotelaria) | 10 | 10 |
| H.1.9 / H.1.10 | Louças e vidros / Talheres e utensílios de cozinha | 33,33 / 50 | 3 / 2 |
| F.1 | Construções ligeiras não afectas a obras em curso (construção) | 12,5 | 8 |
| F.5 | Ferramentas e equipamentos individuais (construção) | 33,33 | 3 |
| J.1.2 | Equipamento de processamento de dados (telecom e TI) | 33,33 | 3 |
| J.1.17 | Centrais de transmissão e recepção por satélite | 20 | 5 |
| K.1.3 | Caixas automáticas (ATM) | 16,67 | 6 |
| K.1.4 | Terminais de pagamento (POS) | 20 | 5 |
| K.1.2 | Cofres e casas fortes | 6,67 | 15 |
| L.1.1 | Edifícios exclusivamente para serviços de saúde | 2,5 | 40 |
| L.1.2 | Equipamento e material médico-cirúrgico | 25 | 4 |
| L.1.13 | Ambulâncias e seus apetrechos | 20 | 5 |
| I.1.2.1 | Veículos automóveis de serviço público (pesados, ligeiros...) (transportes) | 25 | 4 |
| N.1 | Despesas de I&D, patentes, marcas, alvarás e processos de fabrico | 20 | 5 |

**Equipamento escolar ou de ensino:** não existe uma secção ou linha própria. Os edifícios de ensino estão em G.1.5 (4%). O mobiliário e o equipamento seguem a Secção G (por exemplo, G.5.5.x, G.3.x), nos termos do art. 6.º, n.º 5.

**Software:** não está na tabela. Aplica-se o CII art. 39.º, n.º 4, ou seja, **3 anos (33,33%)**.

### 3.3 Sugestão de categorias por defeito para o Odoo (Secção G e CII)

| Categoria | Taxa | Vida | Base |
|---|---|---|---|
| Edifícios habitacionais | 2% | 50 | G.1.4 |
| Edifícios comerciais e administrativos | 4% | 25 | G.1.3 |
| Edifícios industriais | 4% | 25 | G.1.1 |
| Construções ligeiras | 12,5% | 8 | G.1.6 |
| Instalações (água, electricidade, AVAC central) | 10% | 10 | G.2.1 |
| Instalações divisórias de escritório | 20% | 5 | G.2.10 |
| Maquinaria e equipamento não especificado | 12,5% | 8 | G.3.17 |
| Máquinas-ferramentas ligeiras / pesadas | 20% / 12,5% | 5 / 8 | G.3.9 / G.3.10 |
| Equipamento informático (hardware) | 33,33% | 3 | G.3.1 |
| Impressoras | 33,33% | 3 | G.3.4 |
| Telemóveis | 33,33% | 3 | G.3.16 |
| Ar condicionado | 12,5% | 8 | G.3.12 |
| Viaturas ligeiras (limite fiscal Kz 20 M) | 25% | 4 | G.4.1.2 + CII 40.º e) |
| Viaturas mistas | 20% | 5 | G.4.1.3 |
| Viaturas pesadas | 16,67% | 6 | G.4.1.1 |
| Motociclos e bicicletas | 25% | 4 | G.4.4 |
| Mobiliário de madeira / outros materiais | 16,67% / 12,5% | 6 / 8 | G.5.5.1 / G.5.5.2 |
| Ferramentas de oficina / outras | 14,28% / 25% | 7 / 4 | G.5.11 / G.5.12 |
| Software | 33,33% | 3 | CII 39.º, n.º 4 |
| I&D, patentes, marcas | 20% | 5 | N.1 |
| Incorpóreo com período indeterminável | 20% | 5 | CII 39.º, n.º 3 |
| Bens de reduzido valor (≤ Kz 30 000) | 100% no ano | 1 | CII 36.º |

Nota de implementação: no Odoo, a configuração natural é por **vida útil em meses** (por exemplo, 36 meses para 33,33%). A tabela legal tem as duas colunas, taxa e vida, e na grande maioria das linhas são coerentes. Quando não são coerentes (ver 4.2), prevalece a **taxa**, porque o art. 4.º fixa limites de taxas.

---

## 4. Incertezas e problemas encontrados

### 4.1 Transcrição AngoLEX vs PDF oficial

A transcrição do AngoLEX **omite 7 linhas** que existem no PDF oficial e tem 2 gralhas de numeração. Tudo foi corrigido no CSV com base no OCR do PDF:

- Linhas omitidas: DD.2.5, DG.3.3 (Prensas), DI.2.3, DL.1.1 (Fornos e estufas), F.4.5, I.5.8 e I.6.9 (PAPI).
- Gralhas: F.2 aparece numerada "1" no AngoLEX; E.1.2.4 aparece como "1.24".
- Em DD.2.5, a designação exacta tem uma parte ilegível no OCR ("...folheados, contrap lacados e aglomerados...").

### 4.2 Incoerências entre taxa e vida útil no próprio diploma oficial

| Linha | Taxa | Vida | Comentário |
|---|---|---|---|
| B.4.1 Ponte-cais de betão | 3,33 | 3 | Provavelmente 30 anos |
| J.1.19 Cabos submarinos | 6,66 | "120" (AngoLEX "1,20") | Provavelmente 15 anos |
| M.3.5 Edifícios exclusivamente para espectáculos | 4 | 50 | Ou 4% / 25, ou 2% / 50 |

Arredondamentos inconsistentes no original (6,66 vs 6,67; 16,66 vs 16,67; 7,14 vs 7,15) foram mantidos tal como publicados.

### 4.3 Outras incertezas

- **C.1.1** (Secção C, "1. Terrenos") não aparece no PDF: a lista salta para 1.2, "Destinados a entulheiras". Parece ser uma lacuna do próprio original.
- **Vigência:** não foi encontrado nenhum Decreto Executivo de actualização da tabela nem do limite de Kz 30 000. A tabela de 2015 continua a ser a referência conhecida. Confirmar no Diário da República de 2016 a 2026 ou com um consultor.
- **Ano de aquisição (regra anual vs duodécimos):** a lei permite as duas opções (ver 2.3). A leitura de que o regime anual dá uma quota completa no ano de entrada é **interpretação nossa**.
- **Trespasses e despesas de constituição:** não constam da tabela (ver 2.7, interpretação).
- **Reavaliações:** o Decreto n.º 6/96 não foi consultado. A informação sobre o OGE 2026 vem apenas de uma fonte secundária (EY).
- **Contabilidade vs fiscalidade:** este documento trata dos limites **fiscais** (Imposto Industrial). A política contabilística (PGC / Decreto 82/01, ou IFRS) pode usar outras vidas úteis. Nesse caso, a diferença é corrigida na Modelo 1.
