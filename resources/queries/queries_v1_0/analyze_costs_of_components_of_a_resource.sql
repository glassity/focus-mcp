-- Analyze costs of components of a resource
-- Source: https://focus.finops.org/use-case/resource-component-costs/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT ResourceId, ResourceName, ResourceType, ChargeDescription, SkuId, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? AND ChargePeriodEnd < ? AND ResourceId=? GROUP BY ResourceId, ResourceName, ResourceType, ChargeDescription, SkuId