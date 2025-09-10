-- Analyze costs by service name
-- Source: https://focus.finops.org/use-case/costs-service-name/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT BillingPeriodStart, ProviderName, SubAccountId, SubAccountName, ServiceName, SUM(BilledCost) AS TotalBilledCost, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE ServiceName = ? AND BillingPeriodStart >= ? AND BillingPeriodStart < ? GROUP BY BillingPeriodStart, ProviderName, SubAccountId, SubAccountName, ServiceName ORDER BY MonthlyCost DESC