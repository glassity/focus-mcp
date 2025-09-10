-- Identify unused commitments
-- Source: https://focus.finops.org/use-case/identify-unused-commitments/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT MIN(ChargePeriodStart) AS ChargePeriodStart, MAX(ChargePeriodEnd) AS ChargePeriodEnd, ProviderName, BillingAccountId, CommitmentDiscountId, CommitmentDiscountType, CommitmentDiscountStatus, SUM(BilledCost) AS TotalBilledCost, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? AND ChargePeriodEnd < ? AND CommitmentDiscountStatus = 'Unused' GROUP BY ProviderName, BillingAccountId, CommitmentDiscountId, CommitmentDiscountType