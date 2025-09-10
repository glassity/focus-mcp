-- Report service costs by providers subaccount
-- Source: https://focus.finops.org/use-case/report-service-costs-by-providers-subaccount/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT ProviderName, ServiceName, SubAccountId, ChargePeriodStart, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd < ? AND SubAccountId = ? AND ProviderName = ? GROUP BY ProviderName, ServiceName, SubAccountId, ChargePeriodStart ORDER BY SUM(EffectiveCost), BillingPeriodStart DESC