-- Report application cost month over month
-- Source: https://focus.finops.org/use-case/application-cost/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT MONTH(BillingPeriodStart), ServiceName, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE Tags["Application"] = ? AND ChargePeriodStart >= ? AND ChargePeriodEnd < ? GROUP BY MONTH(BillingPeriodStart), ServiceName