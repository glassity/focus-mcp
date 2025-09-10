-- Analyze service costs by region
-- Source: https://focus.finops.org/use-case/analyze-service-costs-by-region/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT ChargePeriodStart, ProviderName, RegionId, ServiceName, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? GROUP BY ChargePeriodStart, ProviderName, RegionId, ServiceName ORDER BY ChargePeriodStart, SUM(EffectiveCost) DESC