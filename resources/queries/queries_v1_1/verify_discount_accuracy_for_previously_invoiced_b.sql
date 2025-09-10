-- Verify discount accuracy for previously invoiced billing period
-- Source: https://focus.finops.org/use-case/verify-discounts-applied/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.1
-- FOCUS Version: v1.1

SELECT ProviderName, BillingAccountId, BillingAccountName, BillingCurrency, ServiceName, SUM(EffectiveCost) AS TotalEffectiveCost, SUM(ListCost) AS TotalListCost, SUM(BilledCost) AS TotalBilledCost, (SUM(EffectiveCost)/SUM(BilledCost))*100 AS EffectiveDiscount FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd < ? AND ChargeClass != 'Correction' GROUP BY ProviderName, BillingAccountId, BillingAccountName, BillingCurrency, ServiceName