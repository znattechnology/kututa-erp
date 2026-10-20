# Fontes: SAF-T (AO)

Descarregado em 20/10/2026. São dados externos: não se executa nada a partir deles.

| Ficheiro | Origem | SHA-256 |
|---|---|---|
| `SAFTAO1.01_01.xsd` (125 559 B) | https://raw.githubusercontent.com/assoft-portugal/SAF-T-AO/master/XSD/SAFTAO1.01_01.xsd (commit `ed86c7d5`, 27/04/2026; `ModificationDate` interno 2024-10-16) | `e9a938e1…2c631` |
| `decreto-executivo-317-20.pdf` (+ `.txt`, texto via pdftotext) | mesmo repositório, `Resources/Legislation/decreto-317-20.pdf` (DR I Série n.º 201, 14/12/2020) | `73be36b6…9e0ec` |
| `decreto-presidencial-312-18.pdf` (+ `-ocr.txt`, OCR por tesseract) | mesmo repositório, `Resources/Legislation/decreto-312-18.pdf` (DR I Série n.º 189, 21/12/2018) | `d008e359…acf53` |
| `decreto-presidencial-71-25.pdf` (+ `-ocr.txt`, OCR) | mesmo repositório, `Resources/Legislation/decreto-71-25.pdf` | `20c12a22…c077b` |
| `TaxExemptions.xml` | mesmo repositório, `Resources/Examples/TaxExemptions.xml` (versão 2.0.0, 2021-01-07, **desactualizada**) | `cbd30b74…37850` |
| `agt-comunicado-saft-facturacao-dispensa.pdf` (+ `-ocr.txt`) | Comunicado AGT de 20/03/2026, via KPMG Angola: https://kpmg.com/content/dam/kpmgsites/ao/pdf/Comunicado-Faturacao.pdf.coredownload.inline.pdf | — |
| `agt-comunicado-saft-contabilidade.pdf` (+ `-ocr.txt`) | Comunicado AGT de 15/04/2026, via KPMG: https://kpmg.com/content/dam/kpmgsites/ao/pdf/Comunicado_AGT.pdf.coredownload.inline.pdf | — |
| `agt-comunicado-circular-saft-inventarios.pdf` (+ `-ocr.txt`) | Comunicado e Circular n.º 05/GACA/GJ/DSF/AGT/2026, de 13/02/2026, via KPMG: https://kpmg.com/content/dam/kpmgsites/ao/pdf/Comunicado-e-Circular-SAF-T-inventarios.pdf.coredownload.pdf | — |
| `arvore-xsd.txt` | Gerado localmente a partir do XSD (árvore de elementos, cardinalidades, tipos e enumerações) | — |

## Notas

- **O XSD não está publicado no site da AGT.** A fonte de referência de facto é o repositório GitHub `assoft-portugal/SAF-T-AO`, mantido pela ASSOFT com contributos da Primavera, SAP, Eticadata e outros. O XSD declara `doc:Author` = "AGT - Administração Geral Tributária" e `doc:Status` = "Development". Não há checksum oficial da AGT contra o qual o comparar.
- A última *release* com etiqueta é `1.01_01.0.008` (11/08/2020). O ramo `master` traz correcções posteriores: GC em WorkingDocuments (2021), TaxBase em WorkingDocuments (2023), TaxCode "INT" (2024) e "Erros novo .xsd" (16/10/2024). **Usa-se o `master`.**
- O DP 312/18, o DP 71/25 e os comunicados AGT são digitalizações. O OCR pode ter erros pontuais: confirmar no PDF qualquer citação literal.
- O DE 683/25 (estrutura de dados da facturação electrónica) já está em `../DE-683-25-ocr.txt`.
- Repositório: https://github.com/assoft-portugal/SAF-T-AO · Portal da AGT (legislação): https://portaldocontribuinte.minfin.gov.ao/legislacao
