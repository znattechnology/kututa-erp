# Fase 3d: SAF-T de inventário (`l10n_ao_stock`)

> **Revisto na auditoria de 2026-10-21** (`auditoria-fase-3.md`): quantidade com o âmbito da valorização (sem consignação nem kits); códigos repetidos e stock negativo recusados; hora de Luanda; assinatura limitada a 500 caracteres, com a chave do produtor em alternativa; custo médio e conta 26.1 por omissão no plano AO; grupos de contabilidade com acesso.

**Estado:** concluída a 2026-10-20. Testes: 7 (`make test m=l10n_ao_stock`). Instalado na base `kututa_demo` (instala o Inventário do Odoo).

**Fonte:** Circular n.º 05/GACA/GJ/DSF/AGT/2026, de 13/02/2026, e o comunicado da mesma data (`docs/referencias/saft-ao/agt-comunicado-circular-saft-inventarios.pdf`). DP 71/25, art. 24.º, n.º 1, al. d): existências a 31/12, a entregar até 15 de Fevereiro no Portal do Contribuinte, em XML, JSON ou Excel.

## O que faz
Inventário › Relatórios (e Contabilidade › Relatórios › Angola (PGC)) › **SAF-T de inventário (AGT)**:
- **Cabeçalho (StockHeader):** assinatura digital, NIF, data de geração, n.º do software validado, nome e versão do software, ano e «Sem operações: Sim» quando não há existências.
- **Tabela de inventário (Stock)**, um registo por artigo com existência a 31/12:

  | Campo | Origem |
  |---|---|
  | Método de custeio | FIFO, ou CMP para custo médio (o custo padrão sai como CMP, com aviso) |
  | Tipo de produto | Campo da categoria; se vazio, a conta de existências do PGC (22 → P, 23 → T, 24 → A, 25 → S, 26 → M); por omissão M |
  | ProductCode | O mesmo da facturação electrónica (referência interna, ou o id do artigo) |
  | ProductDescription, Quantity, UnitOfMeasure | Do artigo, com a quantidade à data |
  | Valor | Valorização do Odoo a 31/12 |

- **Excel** (por omissão): folhas StockHeader e Stock, com as designações da Circular. Também **XML** e **JSON**.
- **Assinatura:** assinatura RS256 (chave do contribuinte ou, na sua falta, do produtor) do cabeçalho e das linhas, em base64url (342 caracteres com uma chave de 2048 bits; o limite é 500).

## A confirmar com a AGT
| Tema | Porquê |
|---|---|
| Etiquetas XML/JSON do método de custeio, do valor, do ano e de «sem operações» | A Circular só as dá em português (saem `MetodoCusteio`, `Valor`, `AAAA`, `SemOperacoes`); a raiz XML (`SAFTInventario`) também não está definida. Por isso o formato por omissão é o Excel |
| O que a «Assinatura» assina | A Circular não define a mensagem nem o algoritmo |
| Serviços `comunicarInventario` / `submeterInventario` da facturação electrónica | Constam da lista de serviços, mas a especificação não foi publicada |
