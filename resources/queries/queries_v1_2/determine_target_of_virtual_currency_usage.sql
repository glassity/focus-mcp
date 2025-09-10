-- Determine target of virtual currency usage
-- Source: https://focus.finops.org/use-case/determine-target-of-virtual-currency-usage/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, PublisherName, ServiceName, ChargeDescription, SUM(PricingCurrencyEffectiveCost) AS TotalPricingCurrencyEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? AND PricingCurrency = ? GROUP BY ProviderName, PublisherName, ServiceName, ChargeDescription ORDER BY TotalPricingCurrencyEffectiveCost DESC LIMIT 10