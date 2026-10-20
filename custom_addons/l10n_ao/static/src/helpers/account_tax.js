import { patch } from "@web/core/utils/patch";
import { roundPrecision } from "@web/core/utils/numbers";

import { accountTaxHelpers } from "@account/helpers/account_tax";

// -------------------------------------------------------------------------
// HELPERS IN BOTH PYTHON/JAVASCRIPT (account_tax.js / models/account_tax.py)
// -------------------------------------------------------------------------

patch(accountTaxHelpers, {
    /**
     * AGT (DE n.º 683/25, taxContribution): o imposto de cada linha é arredondado por excesso
     * ao cêntimo seguinte. Espelho de AccountTax._add_tax_details_in_base_line (l10n_ao).
     */
    add_tax_details_in_base_line(base_line, company, { rounding_method = null } = {}) {
        rounding_method = rounding_method || company.tax_calculation_rounding_method;
        const country_code = company.account_fiscal_country_id?.code;
        if (country_code !== "AO" || rounding_method !== "round_per_line") {
            return super.add_tax_details_in_base_line(base_line, company, { rounding_method });
        }
        super.add_tax_details_in_base_line(base_line, company, { rounding_method: "round_globally" });
        const tax_details = base_line.tax_details;
        const currency_pd = base_line.currency_id.rounding;
        const company_currency_pd = company.currency_id.rounding;
        const rate = base_line.rate || 1.0;
        const round = (amount) => roundPrecision(amount, currency_pd);
        const roundUp = (amount, precision = currency_pd) => roundPrecision(amount, precision, "UP");
        const priceIncluded = tax_details.taxes_data.some((tax_data) => tax_data.price_include);
        const lineBase = round(tax_details.raw_total_excluded_currency);

        // Imposto de cada taxa com a fórmula AGT: base da linha arredondada x taxa, por excesso.
        const taxesFor = (base) =>
            tax_details.taxes_data.map((tax_data) => {
                const tax = tax_data.tax;
                if (tax.amount_type === "percent") {
                    const taxBase = round(tax_data.raw_base_amount_currency) + (base - lineBase);
                    const amount = roundUp((taxBase * tax.amount) / 100.0);
                    // Autoliquidação: o Odoo junta uma parcela simétrica (o total líquido fica a zero).
                    return [taxBase, tax_data.is_reverse_charge ? -amount : amount];
                }
                return [round(tax_data.raw_base_amount_currency), roundUp(tax_data.raw_tax_amount_currency)];
            });
        const sumTaxes = (amounts) => amounts.reduce((sum, [, amount]) => sum + amount, 0);

        let base = lineBase;
        let amounts = taxesFor(base);
        if (priceIncluded) {
            // Preço com imposto incluído: a base é a maior que não ultrapassa o preço de etiqueta.
            const total = round(tax_details.raw_total_included_currency);
            const sign = total < 0 ? -1 : 1;
            for (let attempt = 0; attempt < 3; attempt++) {
                if (round(Math.abs(base + sumTaxes(amounts)) - Math.abs(total)) <= 0) {
                    break;
                }
                base = round(base - sign * currency_pd);
                amounts = taxesFor(base);
            }
        }

        tax_details.raw_total_excluded_currency = base;
        tax_details.raw_total_excluded = roundPrecision(base / rate, company_currency_pd);
        tax_details.taxes_data.forEach((tax_data, index) => {
            const [taxBase, amount] = amounts[index];
            tax_data.raw_base_amount_currency = taxBase;
            tax_data.raw_tax_amount_currency = amount;
            tax_data.raw_base_amount = roundPrecision(taxBase / rate, company_currency_pd);
            tax_data.raw_tax_amount = roundUp(amount / rate, company_currency_pd);
            tax_data.tax_amount = amount;
            tax_data.base_amount = taxBase;
        });
        tax_details.raw_total_included_currency = base + sumTaxes(amounts);
        tax_details.raw_total_included =
            tax_details.raw_total_excluded +
            tax_details.taxes_data.reduce((sum, tax_data) => sum + tax_data.raw_tax_amount, 0);
    },
});
