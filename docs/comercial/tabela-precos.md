# Tabela de preços do Kututa ERP

Aprovada a 30/10/2026. Posicionamento: **ERP completo a meio do mercado**. O Kututa cobra cerca de 3 a 5 vezes o preço do software local de facturação e 35 a 50% do Primavera, e cobra sempre a implementação. Fundamentação em [`docs/estudos/Preços software gestão Angola.md`](../estudos/Preços%20software%20gestão%20Angola.md).

**Esta tabela é só da Vímeo (dona da marca Kututa) para vender o Kututa ERP aos seus clientes. Não é carregada nas bases das empresas clientes:** o script só corre na empresa com o NIF da Vímeo e os produtos ficam presos a essa empresa.

Os preços estão em Kz, sem IVA; acresce o IVA de 14%. A lista completa, com referências e descrições, está em [`tabela-precos.csv`](tabela-precos.csv). É a fonte que carrega os produtos no Odoo: `tools/carregar_tabela_precos.py`.

## Empresas

| Plano | Mensalidade | Incluído | Utilizador adicional | Implementação |
|---|---|---|---|---|
| Essencial | 20 000 | 3 utilizadores, facturação AGT, 1 POS offline, stock, SAF-T | 6 000; caixa POS 5 000 | 75 000 (grátis no anual) |
| Negócio | 55 000 | 5 utilizadores, contabilidade PGC, salários até 25 trabalhadores | 8 000; trabalhador 400 | 350 000 |
| Empresarial | 150 000 | 10 utilizadores, todos os módulos, salários até 100 trabalhadores, 4 h/mês | 9 000; trabalhador 250 | a partir de 1 500 000 |
| Corporativo | a partir de 500 000 | 50 utilizadores, instância dedicada, SLA de 2 h, 8 h/mês | 6 500 | a partir de 5 000 000 |

## Escolas (primário, secundário, técnico-profissional)

O preço é por escala de alunos activos.

| Alunos | Académico | Completo (com contabilidade e salários) | Implementação (Completo; Académico −25%) |
|---|---|---|---|
| até 300 | 35 000 | 50 000 | 200 000 |
| 301–800 | 60 000 | 85 000 | 400 000 |
| 801–1 500 | 90 000 | 125 000 | 600 000 |
| 1 501–3 000 | 130 000 | 180 000 | 900 000 |
| mais de 3 000 | sob proposta | sob proposta | sob proposta |

## Ensino superior

| Estudantes | Mensalidade | Implementação |
|---|---|---|
| até 1 500 | 500 000 | 3 500 000 |
| 1 501–4 000 | 950 000 | 6 000 000 |
| 4 001–8 000 | 1 500 000 | 9 000 000 |
| 8 001–15 000 | 2 300 000 | 14 000 000 |
| mais de 15 000 | sob proposta | sob proposta |

## Serviços avulsos

| Serviço | Preço |
|---|---|
| Diária de consultoria / meia diária | 180 000 / 100 000 |
| Hora remota | 25 000 |
| Pacote pré-pago de 10 h (válido 6 meses) | 220 000 |
| Hora de urgência | 40 000 |
| Formação presencial: meio dia / dia | 100 000 / 180 000 |
| Formação remota (hora) | 20 000 |
| Migração de dados a partir de Excel | 150 000 |
| Migração de saldos | 300 000 |
| Migração de outro ERP | desde 600 000 |
| Migração de histórico académico | desde 200 000 |
| Desenvolvimento à medida (hora) | 25 000 |
| Relatório à medida | desde 150 000 |
| Integração | desde 750 000 |

## Condições

- **Pagamento anual adiantado:** paga 10 mensalidades. **Semestral:** 5% de desconto. **Escolas:** podem pagar em 10 prestações, de Setembro a Junho, sem desconto.
- **Pagamento** em Kz, por transferência bancária ou referência Multicaixa.
- **Implementação das escolas:** pode ser paga em 3 prestações.
- **Implementação do ensino superior:** 40% na assinatura, 40% no arranque das inscrições e 20% no fecho do primeiro semestre.
- **Incluído em todos os planos:** alojamento, cópias de segurança diárias e actualizações legais (AGT, IRT, INSS, SAF-T).
- **Suporte:** remoto em horário laboral. Os tempos de resposta crescem com o plano: dia útil seguinte, 8 h, 4 h e 2 h úteis. O apoio presencial e a formação além do incluído pagam-se à parte.
- **Actualização anual:** nas empresas, em Janeiro, pelo índice de preços do INE (IPC homólogo de Novembro). Nas escolas e no ensino superior, no início do ano lectivo, pelo índice que fixa o reajuste das propinas. Mínimo de 0%, máximo de 15%, aviso com 60 dias de antecedência. Os contratos anuais pagos adiantado mantêm o preço durante 12 meses.
- **Cláusula cambial:** se o câmbio BNA do USD variar mais de 15% face à referência (913 Kz/USD a 29/10/2026), revê-se a parte do preço com custos em divisas, estimada em 25%.

## Por decidir

- **«Cliente fundador» para o Instituto Vovó Eva e o Complexo Escolar LBDF:** sugestão de 25% de desconto vitalício na mensalidade, em troca de servirem de referência pública.
- **Antes de publicar a tabela no site:**
  - pedir propostas reais a um revendedor Primavera e a dois fornecedores escolares;
  - confirmar a fiscalidade com um contabilista: serviço ou royalty, retenção de 6,5%;
  - redigir as condições gerais do contrato.
