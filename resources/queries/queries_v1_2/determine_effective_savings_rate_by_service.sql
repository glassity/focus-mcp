-- Determine Effective Savings Rate by Service
-- Source: https://focus.finops.org/use-case/effective-savings-rate-services/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, ServiceName, SUM(ContractedCost) AS Total ContractedCost, SUM(EffectiveCost) AS TotalEffectiveCost, ((SUM(ContractedCost) - SUM(EffectiveCost))/SUM(ContractedCost)) AS EffectiveSavingsRate FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? GROUP BY ProviderName, ServiceName