-- Compare resource usage month over month
-- Source: https://focus.finops.org/use-case/compare-usage-month-over-month/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT MONTH(ChargePeriodStart), ProviderName, ServiceName, ResourceId, SkuId, ConsumedUnit, SUM(ConsumedQuantity) AS TotalConsumedQuantity FROM focus_data WHERE ChargeCategory='Usage' AND ChargePeriodStart >= ? and ChargePeriodEnd < ? GROUP BY MONTH(ChargePeriodStart), ProviderName, ServiceName, ResourceId, SkuId, ConsumedUnit