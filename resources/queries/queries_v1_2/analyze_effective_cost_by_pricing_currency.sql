-- Analyze effective cost by pricing currency
-- Source: https://focus.finops.org/use-case/analyze-effective-cost-by-pricing-currency/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, PublisherName, ServiceName, PricingCurrency, SUM(PricingCurrencyEffectiveCost) AS TotalPricingCurrencyEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? GROUP BY ProviderName, PublisherName, ServiceName, PricingCurrency