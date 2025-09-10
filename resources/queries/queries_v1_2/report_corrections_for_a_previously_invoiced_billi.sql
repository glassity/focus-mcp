-- Report corrections for a previously invoiced billing period
-- Source: https://focus.finops.org/use-case/report-corrections/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, BillingAccountId, ChargeCategory, ServiceCategory, ServiceName, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd < ? AND ChargeClass = 'Correction' GROUP BY ProviderName, BillingAccountId, ChargeCategory, ServiceCategory, ServiceName