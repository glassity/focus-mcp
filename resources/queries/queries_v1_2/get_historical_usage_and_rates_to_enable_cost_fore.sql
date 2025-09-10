-- Get historical usage and rates to enable cost forecasting
-- Source: https://focus.finops.org/use-case/forecast-costs/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, BillingPeriodStart, BillingPeriodEnd, ServiceCategory, ServiceName, RegionId, RegionName, PricingUnit, SUM(EffectiveCost) AS TotalEffectiveCost, SUM(PricingQuantity) AS TotalPricingQuantity FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd <= ? GROUP BY ProviderName, BillingPeriodStart, BillingPeriodEnd, ServiceCategory, ServiceName, RegionId, RegionName, PricingUnit