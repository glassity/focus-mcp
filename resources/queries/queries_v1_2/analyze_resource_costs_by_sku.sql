-- Analyze resource costs by SKU
-- Source: https://focus.finops.org/use-case/resource-costs-sku/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, ChargePeriodStart, ChargePeriodEnd, SkuId, SkuPriceId, PricingUnit, ListUnitPrice, SUM(PricingQuantity) AS TotalPricingQuantity, SUM(ListCost) AS TotalListCost, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? GROUP BY ProviderName, ChargePeriodStart, ChargePeriodEnd, SkuId, SkuPriceId, PricingUnit, ListUnitPrice ORDER BY ChargePeriodStart ASC LIMIT 100