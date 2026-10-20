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

        tax_details.raw_total_excluded_currency = roundPrecision(
            tax_details.raw_total_excluded_currency,
            currency_pd
        );
        tax_details.raw_total_excluded = roundPrecision(
            tax_details.raw_total_excluded,
            company_currency_pd
        );
        for (const tax_data of tax_details.taxes_data) {
            tax_data.raw_tax_amount_currency = roundPrecision(
                tax_data.raw_tax_amount_currency,
                currency_pd,
                "UP"
            );
            tax_data.raw_tax_amount = roundPrecision(tax_data.raw_tax_amount, company_currency_pd, "UP");
            tax_data.raw_base_amount_currency = roundPrecision(
                tax_data.raw_base_amount_currency,
                currency_pd
            );
            tax_data.raw_base_amount = roundPrecision(tax_data.raw_base_amount, company_currency_pd);
            tax_data.tax_amount = tax_data.raw_tax_amount_currency;
            tax_data.base_amount = tax_data.raw_base_amount_currency;
        }
        tax_details.raw_total_included_currency =
            tax_details.raw_total_excluded_currency +
            tax_details.taxes_data.reduce((sum, tax_data) => sum + tax_data.raw_tax_amount_currency, 0);
        tax_details.raw_total_included =
            tax_details.raw_total_excluded +
            tax_details.taxes_data.reduce((sum, tax_data) => sum + tax_data.raw_tax_amount, 0);
    },
});
