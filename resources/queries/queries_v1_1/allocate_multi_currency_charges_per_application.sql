-- Allocate multi-currency charges per application
-- Source: https://focus.finops.org/use-case/allocate-application-multi-currency/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.1
-- FOCUS Version: v1.1

SELECT Tags["ApplicationId"], ProviderName, BillingAccountId, BillingAccountName, BillingCurrency, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd < ? GROUP BY Tags["ApplicationId"], ProviderName, BillingAccountId, BillingAccountName, BillingCurrency