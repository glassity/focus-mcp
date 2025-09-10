-- Identify anomalous daily spending by subaccount, region, and service
-- Source: https://focus.finops.org/use-case/daily-anomaly-services/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.1
-- FOCUS Version: v1.1

SELECT DATE(ChargePeriodStart) AS Day, ProviderName, SubAccountId, RegionId, RegionName, ServiceName, SUM(EffectiveCost) AS DailyEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? GROUP BY DATE(ChargePeriodStart) AS StartDay, ProviderName, SubAccountId, RegionId, RegionName, ServiceName