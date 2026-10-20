# Fase 3c: SAF-T (AO) (`l10n_ao_saft`)

**Estado:** concluída a 2026-10-20. Testes: 6 (`make test m=l10n_ao_saft`); a bateria dos sete módulos tem 144 testes, 0 falhas. Na base `kututa_demo`, os três tipos de ficheiro de 2026 validam pelo XSD.

**Fontes** (`docs/referencias/saft-ao/`, ver `FONTE.md` e `RESUMO.md`):
- XSD SAFTAO1.01_01 (repositório ASSOFT/AGT, versão de 2024-10-16);
- DE 317/20 (estrutura), DP 312/18 e DP 71/25;
- comunicados da AGT de 20/03/2026 (dispensa do SAF-T de facturação) e 15/04/2026 (contabilidade).

## Obrigações
| Ficheiro | Prazo | Situação |
|---|---|---|
| **Contabilidade** (C ou I) | Anual, até 10 de Abril (DP 71/25, art. 24.º) | **Obrigatório a partir do exercício de 2026** (entrega até 10/04/2027) |
| Facturação (F) | Mensal (DP 312/18) | Dispensado para quem emite facturação electrónica; disponível para pedidos da AGT |
| Inventário | Até 15 de Fevereiro | Estrutura própria (Circular 05/2026): ver a fase 3d |

## O que faz
Relatórios › Angola (PGC) › **SAF-T (AO)**: escolhe-se o tipo e o período (por omissão, o exercício anterior); o ficheiro é **validado pelo XSD** antes de ser descarregado, e os erros aparecem com o número da linha.

| Tipo | Tabelas |
|---|---|
| C, Contabilidade | Cabeçalho, plano de contas com saldos de abertura e de fecho (GR/GA/GM e conta-mãe), clientes, fornecedores, tabela de impostos, lançamentos (diários e transacções) |
| I, Contabilidade integrada com facturação | C + produtos + facturas e talões (4.1) + recibos (4.4) + facturas de fornecedor (4.5) |
| F, Facturação | Cabeçalho, clientes, produtos, impostos, facturas e talões, recibos |

- **Facturas, talões e recibos** vêm do documento AGT fixado na emissão (`l10n_ao_edi_payload`), o mesmo que foi comunicado à AGT. Os documentos emitidos antes da fixação reconstroem-se a partir do registo. Os rejeitados pela AGT saem como anulados (A).
- **Consumidor final:** cliente «CF», NIF 999999999.
- **Lançamentos:** TransactionID «data diário n.º de arquivo»; o apuramento de resultados (3a) sai como tipo A, os restantes como N; cada factura liga-se à sua transacção.
- **Software:** NIF e nome do produtor na ficha da empresa (separador AGT); o SoftwareValidationNumber só sai quando tiver o formato NNN/AGT/AAAA, senão «0».

## Pendente
| Tema | Motivo |
|---|---|
| **Hash dos documentos** (172 caracteres) | O algoritmo está no DE 74/19, que não foi obtido. Sai «0» / HashControl «0», o valor previsto para programas não validados |
| IVA dedutível por tipo (Deductible, MFI/INV/OBC/SERV/IMPT/SCE) nas facturas de fornecedor | Opcional no XSD; falta classificar as compras |
| WorkingDocuments (pró-formas, orçamentos) e MovementOfGoods (guias) | O Kututa ainda não emite estes documentos como documentos AGT |
| Um ficheiro de facturação por estabelecimento | Hoje é «Global» |
| Submissão no Portal do Contribuinte | Feita à mão pelo contribuinte (sem serviço web) |
