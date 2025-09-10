-- Determine contracted savings by virtual currency
-- Source: https://focus.finops.org/use-case/determine-contracted-savings-by-virtual-currency/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ServiceName, ServiceSubcategory, ChargeDescription, BillingCurrency, PricingCurrency, SUM(PricingCurrencyListUnitPrice-PricingCurrencyContractedUnitPrice) AS ContractedSavingsInPricingCurrency SUM(ListUnitPrice - ContractedUnitPrice) AS ContractedSavingsInBillingCurrency FROM focus_data_tabl WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? AND PricingCurrencyListUnitPrice > PricingCurrencyContractedUnitPrice GROUP BY ServiceName, ServiceSubcategory, ChargeDescription, BillingCurrency, PricingCurrency