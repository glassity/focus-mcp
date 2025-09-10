-- Update budgets with billed costs
-- Source: https://focus.finops.org/use-case/update-budgets/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, BillingPeriodStart, BillingPeriodEnd, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd < ? GROUP BY ProviderName, BillingPeriodStart, BillingPeriodEnd