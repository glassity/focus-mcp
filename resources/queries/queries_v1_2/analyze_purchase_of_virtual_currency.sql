-- Analyze purchase of virtual currency
-- Source: https://focus.finops.org/use-case/analyze-purchase-of-virtual-currency/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, PublisherName, ChargeDescription, PricingUnit, BillingCurrency, SUM(PricingQuantity) AS TotalPricingQuantity, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? AND ChargeCategory = 'Purchase' AND PricingUnit = ? GROUP BY ProviderName, PublisherName, ChargeDescription, PricingUnit, BillingCurrency