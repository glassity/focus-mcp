-- Analyze costs by availability zone for a subaccount
-- Source: https://focus.finops.org/use-case/costs-by-availability-zone/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT ProviderName, RegionName, AvailabilityZone, BillingPeriodStart, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE SubAccountId = ? AND ChargePeriodStart >= ? AND ChargePeriodEnd < ? GROUP BY ProviderName, RegionName, AvailabilityZone, BillingPeriodStart ORDER BY ProviderName, RegionName, AvailabilityZone, BillingPeriodStart