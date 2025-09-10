-- Report costs by service category and subcategory
-- Source: https://focus.finops.org/use-case/report-costs-by-service-category-and-subcategory/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, BillingCurrency, BillingPeriodStart, ServiceCategory, ServiceSubcategory, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE BillingPeriodStart >= ? and BillingPeriodEnd < ? GROUP BY ProviderName, BillingCurrency, BillingPeriodStart, ServiceCategory, ServiceSubcategory ORDER BY TotalBilledCost DESC