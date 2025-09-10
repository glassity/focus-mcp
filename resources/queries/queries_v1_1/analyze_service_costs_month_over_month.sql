-- Analyze service costs month over month
-- Source: https://focus.finops.org/use-case/service-costs-month-over-month/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.1
-- FOCUS Version: v1.1

SELECT MONTH(ChargePeriodStart), ProviderName, ServiceName, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? AND ChargePeriodStart < ? GROUP BY MONTH(ChargePeriodStart), ProviderName, ServiceName ORDER BY MONTH(ChargePeriodStart), SUM(EffectiveCost) DESC