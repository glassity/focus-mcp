-- Verify accuracy of provider invoices
-- Source: https://focus.finops.org/use-case/verify-invoices/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT ProviderName, BillingAccountId, BillingAccountName, BillingCurrency, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd < ? GROUP BY ProviderName, BillingAccountId, BillingAccountName, BillingCurrency