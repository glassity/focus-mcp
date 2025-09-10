-- Report recurring charges for commitment-based discounts over a period
-- Source: https://focus.finops.org/use-case/recurring-commitment-charges/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT BillingPeriodStart, CommitmentDiscountId, CommitmentDiscountName, CommitmentDiscountType, ChargeFrequency, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodStart < ? AND ChargeFrequency = 'Recurring' AND CommitmentDiscountId IS NOT NULL GROUP BY BillingPeriodStart, CommitmentDiscountId, CommitmentDiscountName, CommitmentDiscountType, ChargeFrequency