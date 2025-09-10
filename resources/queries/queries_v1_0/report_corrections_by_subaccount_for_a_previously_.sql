-- Report corrections by subaccount for a previously invoiced billing period
-- Source: https://focus.finops.org/use-case/corrections-by-subaccount/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT ProviderName, BillingAccountId, ServiceCategory, SubAccountId, SubAccountName, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd < ? AND ChargeClass = 'Correction' GROUP BY ProviderName, BillingAccountId, SubAccountId, SubAccountName, ServiceCategory