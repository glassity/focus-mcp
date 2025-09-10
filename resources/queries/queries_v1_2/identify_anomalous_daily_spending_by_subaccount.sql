-- Identify anomalous daily spending by subaccount
-- Source: https://focus.finops.org/use-case/daily-anomaly-subaccount/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT DATE(ChargePeriodStart) AS Day, ProviderName, SubAccountId, SUM(EffectiveCost) AS DailyEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? GROUP BY DATE(ChargePeriodStart) AS StartDay, ProviderName, SubAccountId