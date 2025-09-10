-- Analyze service costs by subaccount
-- Source: https://focus.finops.org/use-case/service-costs-subaccount/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ChargePeriodStart, SubAccountId, SubAccountName, ServiceName, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE SubAccountID = ? AND ChargePeriodStart >= ? AND ChargePeriodEnd < ? GROUP BY ChargePeriodStart, SubAccountId, SubAccountName, ServiceName ORDER BY SUM(EffectiveCost) DESC LIMIT 10