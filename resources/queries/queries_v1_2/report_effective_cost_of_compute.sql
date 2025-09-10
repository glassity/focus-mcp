-- Report effective cost of compute
-- Source: https://focus.finops.org/use-case/effective-cost-compute/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT CommitmentDiscountType, ProviderName, ServiceName, SubAccountId, SubAccountName, BillingPeriodStart, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd <= ? AND ServiceCategory = 'Compute' GROUP BY CommitmentDiscountType, ServiceName, ProviderName, SubAccountId, SubAccountName, BillingPeriodStart