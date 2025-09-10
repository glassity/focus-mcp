-- Determine Effective Savings Rate
-- Source: https://focus.finops.org/use-case/effective-savings-rate/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, EffectiveCost, ((ListCost - EffectiveCost)/ListCost) AS ESROverList, ((ContractedCost - EffectiveCost)/ContractedUnitPrice) AS ESROverContract FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ?