-- Report commitment discount purchases
-- Source: https://focus.finops.org/use-case/commitment-discount-purchases/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.1
-- FOCUS Version: v1.1

SELECT MIN(ChargePeriodStart) AS ChargePeriodStart, MAX(ChargePeriodEnd) AS ChargePeriodEnd, ProviderName, BillingAccountId, CommitmentDiscountId, CommitmentDiscountType, CommitmentDiscountUnit, CommitmentDiscountQuantity, ChargeFrequency, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE ChargePeriodStart >= ? AND ChargePeriodEnd < ? AND ChargeCategory = 'Purchase' AND CommitmentDiscountId IS NOT NULL GROUP BY ProviderName, BillingAccountId, CommitmentDiscountId, CommitmentDiscountType, CommitmentDiscountUnit, CommitmentDiscountQuantity, ChargeFrequency