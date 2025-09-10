-- Analyze cost per compute service for a subaccount
-- Source: https://focus.finops.org/use-case/cost-compute-subaccount/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT Min(ChargePeriodStart), Max(ChargePeriodEnd), ServiceName, ResourceId, ResourceName, SUM(PricingQuantity), SUM(EffectiveCost) AS MonthlyEffectiveCost FROM focus_data WHERE SubAccountId = ? AND ServiceCategory = 'Compute' AND ChargePeriodStart >= ? and ChargePeriodEnd < ? GROUP BY ServiceName, ResourceId, ResourceName ORDER BY MonthlyEffectiveCost DESC