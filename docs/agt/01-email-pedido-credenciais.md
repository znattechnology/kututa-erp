# Fase 0b: pedido de credenciais à AGT (rascunho, enviar manualmente)

**Para:** produtores.dfe.dcrr.agt@minfin.gov.ao
**Assunto:** Pedido de credenciais de acesso à API de Facturação Electrónica (homologação): produtor de software

---

Exmos. Senhores,

Vimos, por este meio, solicitar a atribuição de credenciais de acesso ao ambiente de **homologação** (`sifphml.minfin.gov.ao`) da API de Facturação Electrónica, na qualidade de **produtor de software de facturação**. O pedido é feito ao abrigo do Decreto Presidencial n.º 71/25, de 20 de Março, e do Decreto Executivo n.º 683/25, de 22 de Agosto.

**Dados do produtor:**
- Denominação: `[NOME DA EMPRESA]`
- NIF: `[NIF]`
- Morada: `[MORADA]`
- Responsável técnico: `[NOME]`, `[TELEFONE]`, `[EMAIL]`

**Software:**
- Nome comercial: `[NOME DO PRODUTO]`, ERP baseado em Odoo 20
- Versão: `1.0.0`
- Âmbito: facturação (FT, FR, NC, ND, RC, FA, FG), ponto de venda (TV), compras (validação de documentos de fornecedores) e gestão escolar (propinas)

Solicitamos ainda informação sobre:
1. O procedimento e os requisitos para a **certificação do software** e a obtenção do *softwareValidationNumber*.
2. O registo das chaves públicas no **Portal do Parceiro** (`portaldoparceiro.hml.minfin.gov.ao`).
3. O **esquema XSD do SAF-T (AO)** em vigor.
4. A confirmação do **URL a codificar no QR Code**. O Anexo III do DE 683/25 refere `portaldocontribuinte.minfin.gov.ao/consultar-fe`, enquanto a documentação técnica actual refere `quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe`.

Com os melhores cumprimentos,

`[NOME]`
`[CARGO]`, `[EMPRESA]`

---

## Checklist da Fase 0b
- [ ] Enviar este email (preencher os campos entre `[ ]`)
- [ ] Registo no Portal do Parceiro (homologação)
- [ ] Gerar o par de chaves RSA do **produtor** (4096 bits). A chave privada nunca sai do ambiente do produtor. Comando sugerido: `openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out produtor_private.pem && openssl pkey -in produtor_private.pem -pubout -out produtor_public.pem`
- [ ] Submeter a chave pública no Portal do Parceiro
- [ ] Receber as credenciais Basic Auth de homologação
- [ ] Empresa de teste: obter as chaves do **contribuinte** no Portal do Contribuinte (para o `jwsDocumentSignature`)
- [ ] Decidir entre certificação própria e integrador até **15/11/2026**
