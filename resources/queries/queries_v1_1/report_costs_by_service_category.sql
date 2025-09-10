-- Report costs by service category
-- Source: https://focus.finops.org/use-case/costs-service-category/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.1
-- FOCUS Version: v1.1

SELECT ProviderName, BillingCurrency, BillingPeriodStart, ServiceCategory, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE BillingPeriodStart >= ? and BillingPeriodEnd <= ? GROUP BY ProviderName, BillingCurrency, BillingPeriodStart, ServiceCategory ORDER BY TotalBilledCost DESC