# Fase 4: Kututa Kazi, recursos humanos e salários (`l10n_ao_hr`, `l10n_ao_payroll`)

**Estado:** concluída a 2026-10-21. Testes: 8 no `l10n_ao_hr` e 17 no `l10n_ao_payroll` (12 deles são os casos dourados do motor de cálculo, iguais aos do secPed-Express). Instalado na base `kututa_demo`.

**Fontes** (`docs/referencias/salarios/`): `IRT-INSS.md` (Lei 14/25, CIRT com a Lei 28/20, DP 227/18), `SALARIO-MINIMO.md` (DP 152/24), `FERIADOS.md` (Lei 10/11 com a Lei 11/18), `secped-folha.md` (regras e casos de teste do secPed) e `docs/analise-legal/03-rh-LGT-12-23.md`.

## Decisões face ao secPed
| Tema | secPed | Kututa | Porquê |
|---|---|---|---|
| INSS sobre alimentação e transporte | Isentos até 30 000 Kz | **Sujeitos na totalidade** | DP 227/18: só o subsídio de férias e as prestações sociais ficam fora da base |
| INSS sobre o subsídio de férias | Sujeito | **Isento** | DP 227/18, art. 6.º |
| Abono de família | Sem regra | Isento de IRT até 5% do salário base e fora do INSS | CIRT, art. 2.º |
| Contas finais | Sem IRT/INSS | Entram na folha do mês, com IRT; a compensação fica fora do INSS | CIRT, art. 2.º (compensações tributadas) |
| Feriados | Tabela manual | Gerados por regra (datas móveis e pontes) | Lei 10/11, arts. 2.º e 6.º |

## `l10n_ao_hr` (Lei Geral do Trabalho)
- **Contratos** (na ficha do trabalhador, separador «Folha»): tipo (indeterminado, termo certo, termo incerto, comissão de serviço, aprendizagem, estágio), causa do termo (art. 15.º, a–k) com a duração máxima (art. 16.º) contada com as renovações sucessivas, período experimental com os máximos do art. 18.º (30/60/120/180 dias) e preenchido por omissão no primeiro contrato, base de pagamento (mensal, por tempo lectivo, misto) e horas semanais (44 por omissão). Aviso 30 dias antes do fim do contrato a termo (art. 17.º), por cron.
- **Ausências:** 17 tipos da LGT com limites por evento, mês e ano (arts. 222.º a 229.º), validados ao aprovar; faltas injustificadas acima de 3/mês ou 12/ano, e 10 dias seguidos (abandono), criam uma actividade ao RH (arts. 230.º e 306.º).
- **Feriados nacionais:** os 12 da Lei 10/11, as pontes (terça → segunda; quinta → sexta) e as tardes de 24 e 31 de Dezembro, gerados por ano e por empresa (botão na empresa e cron em Novembro para o ano seguinte).
- **Horários:** calendários «Angola: 44 horas» (segunda a sábado) e «40 horas».
- **Trabalho extraordinário:** registo por tipo (extraordinário, nocturno, dia de descanso, feriado) com aprovação e limites do art. 185.º (2 h/dia, 40 h/mês, 200 h/ano), salvo autorização da IGT.
- **Sanções disciplinares:** redução de salário até 20% por 1 a 6 meses (art. 87.º), suspensão, admoestação.
- **Trabalhador:** n.º de segurado do INSS, data de admissão e antiguidade (art. 311.º: fracção de 3 meses conta como um ano). Motivos de cessação da LGT.

## `l10n_ao_payroll` (folha de salários)
Menu Funcionários › Salários.
- **Folha mensal** por empresa: Calcular → rever → Fechar e contabilizar. Um recibo por trabalhador com contrato em vigor no mês; a proporção é por dias úteis com contrato.
- **Motor de cálculo** (`tools/payroll_calc.py`, puro): salário-hora (art. 237.º/7), tempos lectivos, componentes fixas (alimentação, transporte, renda, abono de família, gratificação, abono para falhas), horas extra +50%/+75% com o limiar de 30 h e o arredondamento do art. 188.º, nocturno +20%, descanso +75%, feriado +100%, subsídio de férias (no mês em que começam, uma vez por ano) e de Natal (proporcional aos meses do ano), faltas não pagas em horas, sanção, INSS 3%/8%, IRT pela tabela em vigor na data (escalões parametrizáveis), adiantamentos até 25% do líquido (art. 248.º/7). Ordem: bruto → faltas → sanção → INSS → IRT → adiantamento.
- **Adiantamentos:** concessão limitada a 3 salários (art. 248.º/6), lançamento D 36.3 / C caixa ou banco, amortização automática ao fechar a folha.
- **Fecho:** numeração dos recibos (AAAA/NNNNN), lançamento no diário «Salários»: D 72.2 (bruto − faltas − sanções), D 72.5.2 (INSS 8%), C 36.1.2 por trabalhador (líquido), C 34.3.1 (IRT), C 34.9.1 (INSS 3% + 8%), C 36.3 (adiantamentos).
- **Saídas:** recibo (art. 247.º: empregador, trabalhador, n.º INSS, período, remunerações, descontos, líquido), folha colectiva, ficheiro bancário (CSV genérico), mapa mensal de remunerações para a AGT e folha do INSS (Excel).
- **Contas finais** (assistente «Contas finais» no trabalhador): antiguidade, compensação pelos arts. 307.º a 310.º conforme o motivo, falta de aviso prévio, férias vencidas e proporcionais (art. 212.º), subsídios proporcionais (art. 238.º/3); regista a saída e cria o recibo de contas finais na folha do mês.
- **Avisos** no recibo: salário abaixo do mínimo nacional (100 000 Kz), tabela do IRT em falta, n.º INSS em falta.

## Casos dourados (do secPed, todos a passar)
Salário-hora 220 000/44 h = 1 153,85; IRT: 150 000 → 0, 160 000 → 14 100, 200 000 → 20 500, 300 000 → 49 250, 12 000 000 → 2 842 250; efectivo de 200 000: INSS 6 000, IRT 19 540, líquido 174 460; 35 h extra: 47 202,80 + 9 178,32; faltas 2 dias em 220 000: 20 307,69; sanção 20%: 40 000 e líquido 141 868; adiantamento em 100 000: 24 250; compensações 307.º/308.º/309.º/310.º.

## A confirmar
| Tema | Porquê |
|---|---|
| Formato do mapa mensal de remunerações (Portal do Contribuinte) e da folha electrónica do INSS | Os modelos exigem login; os ficheiros saem em Excel com as colunas conhecidas |
| Formato do ficheiro bancário (PSX/Multicaixa) | Sem especificação; sai um CSV genérico |
| Regime anual do subsídio de Natal para quem entra a meio do ano e tributação «em separado» dos subsídios | Sem base legal expressa; somam ao mês |
| Tempos lectivos | Introduzidos à mão no recibo até o módulo académico (fase 5) os apurar |
| Férias: o plano de acumulação do Odoo (22 dias; 2 por mês no ano de admissão, mínimo 6) | Configuração por empresa, ainda não automatizada |
