-- Forecast amortized costs month over month based on historical trends
-- Source: https://focus.finops.org/use-case/forecast-amortized-costs/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT MONTH(BillingPeriodStart), ProviderName, ServiceCategory, ServiceName, ChargeCategory, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd < ? GROUP BY MONTH(BillingPeriodStart), ProviderName, ServiceCategory, ServiceName, ChargeCategory