-- Forecast cashflow month over month based on historical trends by service
-- Source: https://focus.finops.org/use-case/forecast-cashflow/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT MONTH(BillingPeriodStart), ProviderName, ServiceCategory, ServiceName SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE BillingPeriodStart >= ? AND BillingPeriodEnd < ? GROUP BY MONTH(BillingPeriodStart), ProviderName, ServiceCategory, ServiceName