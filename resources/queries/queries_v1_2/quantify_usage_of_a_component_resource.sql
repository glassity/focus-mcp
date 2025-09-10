-- Quantify usage of a component resource
-- Source: https://focus.finops.org/use-case/quantify-usage-of-a-component-resource/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, ServiceName, PricingUnit, RegionName, JSON_UNQUOTE(JSON_EXTRACT(SkuPriceDetails, '$.InstanceSeries')) AS InstanceSeries, SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(SkuPriceDetails, '$.CoreCount')) AS UNSIGNED)) AS TotalCoreCount FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? AND JSON_CONTAINS_PATH(SkuPriceDetails, 'all', '$.CoreCount', '$.InstanceSeries') GROUP BY ProviderName, ServiceName, PricingUnit, RegionName, InstanceSeries