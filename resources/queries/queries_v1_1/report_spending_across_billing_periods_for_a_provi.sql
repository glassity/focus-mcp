-- Report spending across billing periods for a provider by service category
-- Source: https://focus.finops.org/use-case/report-spending-across-billing-periods-by-service-category/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.1
-- FOCUS Version: v1.1

SELECT ProviderName, BillingAccountName, BillingAccountId, BillingCurrency, BillingPeriodStart, ServiceCategory, ServiceName, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? AND ProviderName = ? GROUP BY ProviderName, BillingAccountName, BillingAccountId, BillingCurrency, BillingPeriodStart, ServiceCategory, ServiceName ORDER BY TotalBilledCost DESC