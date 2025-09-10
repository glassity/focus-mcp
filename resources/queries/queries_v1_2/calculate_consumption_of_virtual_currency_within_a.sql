-- Calculate consumption of virtual currency within a billing period
-- Source: https://focus.finops.org/use-case/calculate-consumption-of-virtual-currency-within-a-billing-period/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, SUM(PricingCurrencyEffectiveCost) AS TotalPricingCurrencyEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? AND PricingCurrency = ? AND ChargeCategory = 'Usage' GROUP BY ProviderName ORDER BY TotalPricingCurrencyEffectiveCost DESC LIMIT 10