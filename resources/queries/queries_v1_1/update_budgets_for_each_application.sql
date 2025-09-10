-- Update budgets for each application
-- Source: https://focus.finops.org/use-case/update-application-budgets/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.1
-- FOCUS Version: v1.1

SELECT ProviderName, BillingPeriodStart, BillingPeriodEnd, Tags["Application"] AS Application SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd < ? GROUP BY ProviderName, BillingPeriodStart, BillingPeriodEnd, Tags["Application"]